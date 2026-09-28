import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { gunzipSync } from 'node:zlib';
import {
  buildReplaySegments,
  canonicalStringify,
  isReplayEvent,
} from './replay';
import { replayItem, replayMetaItem } from './test-fixtures';
import { describe, expect, it } from 'vitest';

describe('Replay segmentation', () => {
  it('uses Go-compatible UTF-8 key order and JSON string escaping', () => {
    expect(
      canonicalStringify({
        _: 'underscore',
        a: 'lowercase',
        a_a: 'underscore-tail',
        'a-a': 'hyphen-tail',
        Z: 'uppercase',
        1: 'integer-key',
        html: '<span>&</span>',
        line: '\u2028\u2029',
        lone: '\ud800',
      }),
    ).toBe(
      '{"1":"integer-key","Z":"uppercase","_":"underscore","a":"lowercase","a-a":"hyphen-tail","a_a":"underscore-tail","html":"<span>&</span>","line":"\\u2028\\u2029","lone":"�"}',
    );
  });

  it('keeps paired surrogates and replaces only unpaired ones', () => {
    expect(
      canonicalStringify({
        broken: 'a\udc00b\ud800',
        emoji: '😀',
        pairThenLone: '😀\ud800',
      }),
    ).toBe('{"broken":"a�b�","emoji":"😀","pairThenLone":"😀�"}');
  });

  it('matches the exact envelope accepted by the Go receiver', async () => {
    const meta = replayMetaItem(
      1,
      'https://shop.example.test/checkout?token=a&next=<checkout>#frag',
    );
    const snapshot = replayItem({
      type: 2,
      timestamp: 2,
      data: {
        node: {
          type: 0,
          id: 1,
          childNodes: [
            {
              type: 2,
              id: 2,
              isSVG: true,
              tagName: 'svg',
              attributes: {
                viewBox: '0 0 24 24',
                preserveAspectRatio: 'xMidYMid',
                data_a: 'underscore',
                'data-a': 'hyphen',
              },
              childNodes: [
                {
                  type: 3,
                  id: 3,
                  textContent: 'masked <>& \u2028 \u2029 \ud800',
                },
              ],
            },
          ],
        },
        initialOffset: { left: 0, top: 0 },
      },
    });
    meta.meta.user = undefined;
    snapshot.meta.user = undefined;

    const [segment] = await buildReplaySegments([meta, snapshot], {
      recordingId: 'recording-01',
      firstSequence: 0,
      maxEvents: 50,
      targetUncompressedBytes: 256 * 1024,
    });
    const actual = gunzipSync(segment!.body).toString('utf8');
    const golden = readFileSync(
      resolve(
        import.meta.dirname,
        '../testdata/faro_transport_envelope.golden.json',
      ),
      'utf8',
    ).trim();

    expect(actual).toBe(golden);
  });

  it('recognizes only Faro ReplayInstrumentation event payloads', () => {
    expect(isReplayEvent(replayItem({ type: 2, timestamp: 1 }))).toBe(true);
    const malformed = replayItem({ type: 2 });
    malformed.payload.attributes = {};
    expect(isReplayEvent(malformed)).toBe(false);
  });

  it('creates versioned gzip envelopes with a full-snapshot marker', async () => {
    const segments = await buildReplaySegments(
      [
        replayMetaItem(1),
        replayItem({ type: 2, timestamp: 1, data: { node: { id: 1 } } }),
        replayItem({ type: 3, timestamp: 2, data: { source: 1 } }),
      ],
      {
        recordingId: 'recording-01',
        firstSequence: 7,
        maxEvents: 50,
        targetUncompressedBytes: 256 * 1024,
      },
    );

    expect(segments).toHaveLength(1);
    expect(segments[0]).toMatchObject({
      sequence: 7,
      hasFullSnapshot: true,
      checksum: expect.stringMatching(/^[a-f0-9]{64}$/),
      segmentId: expect.stringMatching(/^[a-f0-9]{64}$/),
    });
    const envelope = JSON.parse(gunzipSync(segments[0]!.body).toString('utf8'));
    expect(envelope).toMatchObject({
      schema_version: 1,
      application: 'checkout',
      session_id: 'session-01',
      user_id: 'user-pseudonym',
      page_id: 'recording-01',
      recording_id: 'recording-01',
      sequence: 7,
      has_full_snapshot: true,
      event_count: 3,
    });
    expect(
      envelope.events.map((event: { type: number }) => event.type),
    ).toEqual([4, 2, 3]);
    expect(envelope.events).toHaveLength(3);
    const { checksum_sha256: checksum, ...unsigned } = envelope;
    expect(checksum).toBe(
      createHash('sha256').update(JSON.stringify(unsigned)).digest('hex'),
    );
    expect(envelope).not.toHaveProperty('sessionId');
    expect(envelope).not.toHaveProperty('startMs');
  });

  it('supports anonymous sessions and only accepts safe explicit Faro user.id values', async () => {
    const anonymousMeta = replayMetaItem(1);
    const anonymousSnapshot = replayItem({ type: 2, timestamp: 2 });
    anonymousMeta.meta.user = undefined;
    anonymousSnapshot.meta.user = undefined;
    const anonymousSegments = await buildReplaySegments(
      [anonymousMeta, anonymousSnapshot],
      {
        recordingId: 'recording-01',
        firstSequence: 0,
        maxEvents: 50,
        targetUncompressedBytes: 256 * 1024,
      },
    );
    const anonymousEnvelope = JSON.parse(
      gunzipSync(anonymousSegments[0]!.body).toString('utf8'),
    );
    expect(anonymousEnvelope).not.toHaveProperty('user_id');

    const unsafeMeta = replayMetaItem(1);
    const unsafeSnapshot = replayItem({ type: 2, timestamp: 2 });
    unsafeMeta.meta.user!.id = 'customer@example.test';
    unsafeSnapshot.meta.user!.id = 'customer@example.test';
    await expect(
      buildReplaySegments([unsafeMeta, unsafeSnapshot], {
        recordingId: 'recording-01',
        firstSequence: 0,
        maxEvents: 50,
        targetUncompressedBytes: 256 * 1024,
      }),
    ).rejects.toThrow('user.id');

    const otherUser = replayItem({ type: 3, timestamp: 2 });
    otherUser.meta.user!.id = 'user-other';
    await expect(
      buildReplaySegments([replayItem({ type: 2, timestamp: 1 }), otherUser], {
        recordingId: 'recording-01',
        firstSequence: 0,
        maxEvents: 50,
        targetUncompressedBytes: 256 * 1024,
      }),
    ).rejects.toThrow('cannot mix applications, sessions, or users');
  });

  it('splits oversized event batches without changing event order', async () => {
    const segments = await buildReplaySegments(
      [
        replayMetaItem(1),
        replayItem({ type: 2, timestamp: 2 }),
        replayItem({ type: 3, timestamp: 3 }),
        replayItem({ type: 3, timestamp: 4 }),
      ],
      {
        recordingId: 'recording-01',
        firstSequence: 0,
        maxEvents: 2,
        targetUncompressedBytes: 256 * 1024,
      },
    );

    expect(segments.map((segment) => segment.sequence)).toEqual([0, 1]);
    const timestamps = segments.flatMap((segment) => {
      const envelope = JSON.parse(gunzipSync(segment.body).toString('utf8'));
      return envelope.events.map(
        (event: { timestamp: number }) => event.timestamp,
      );
    });
    expect(timestamps).toEqual([1, 2, 3, 4]);
  });

  it('keeps the initial rrweb Meta and a large FullSnapshot in sequence zero', async () => {
    const segments = await buildReplaySegments(
      [
        replayMetaItem(1),
        replayItem({
          type: 2,
          timestamp: 2,
          data: { node: { id: 1, text: 'x'.repeat(300 * 1024) } },
        }),
        replayItem({ type: 3, timestamp: 3, data: { source: 1 } }),
      ],
      {
        recordingId: 'recording-01',
        firstSequence: 0,
        maxEvents: 1,
        targetUncompressedBytes: 256 * 1024,
      },
    );

    expect(segments.map((segment) => segment.sequence)).toEqual([0, 1]);
    const bootstrap = JSON.parse(
      gunzipSync(segments[0]!.body).toString('utf8'),
    );
    expect(
      bootstrap.events.map((event: { type: number }) => event.type),
    ).toEqual([4, 2]);
    expect(segments[0]).toMatchObject({ hasFullSnapshot: true, eventCount: 2 });
  });

  it('keeps every nonzero Meta and large FullSnapshot checkpoint atomic', async () => {
    const segments = await buildReplaySegments(
      [
        replayMetaItem(10),
        replayItem({
          type: 2,
          timestamp: 11,
          data: { node: { id: 1, text: 'x'.repeat(300 * 1024) } },
        }),
        replayItem({ type: 3, timestamp: 12, data: { source: 1 } }),
      ],
      {
        recordingId: 'recording-01',
        firstSequence: 7,
        maxEvents: 1,
        targetUncompressedBytes: 256 * 1024,
      },
    );

    expect(segments.map((segment) => segment.sequence)).toEqual([7, 8]);
    const checkpoint = JSON.parse(
      gunzipSync(segments[0]!.body).toString('utf8'),
    );
    expect(
      checkpoint.events.map((event: { type: number }) => event.type),
    ).toEqual([4, 2]);
    expect(segments[0]).toMatchObject({ hasFullSnapshot: true, eventCount: 2 });
  });

  it('refuses a sequence-zero segment unless Meta and FullSnapshot are first', async () => {
    const segments = await buildReplaySegments(
      [
        replayItem({ type: 3, timestamp: 1, data: { source: 1 } }),
        replayMetaItem(2),
        replayItem({ type: 2, timestamp: 3 }),
      ],
      {
        recordingId: 'recording-01',
        firstSequence: 0,
        maxEvents: 50,
        targetUncompressedBytes: 256 * 1024,
      },
    );

    expect(segments).toEqual([]);
  });

  it('seals a segment when the Replay window crosses five seconds', async () => {
    const segments = await buildReplaySegments(
      [
        replayMetaItem(1_000),
        replayItem({ type: 2, timestamp: 1_000 }),
        replayItem({ type: 3, timestamp: 5_999 }),
        replayItem({ type: 3, timestamp: 6_001 }),
      ],
      {
        recordingId: 'recording-01',
        firstSequence: 0,
        maxEvents: 50,
        targetDurationMs: 5_000,
        targetUncompressedBytes: 256 * 1024,
      },
    );

    expect(segments.map((segment) => segment.eventCount)).toEqual([3, 1]);
  });

  it('fails the entire build when one event exceeds the hard limit', async () => {
    const dropped: string[] = [];
    const segments = await buildReplaySegments(
      [
        replayMetaItem(1),
        replayItem({ type: 2, timestamp: 2 }),
        replayItem({
          type: 3,
          timestamp: 3,
          data: 'x'.repeat(4 * 1024 * 1024 + 1),
        }),
        replayItem({ type: 3, timestamp: 4 }),
      ],
      {
        recordingId: 'recording-01',
        firstSequence: 0,
        maxEvents: 50,
        onDrop: (reason) => dropped.push(reason),
        targetUncompressedBytes: 256 * 1024,
      },
    );

    expect(dropped).toEqual(['event-too-large']);
    expect(segments).toEqual([]);
  });

  it('does not return a later nonzero chunk after an oversized segment', async () => {
    const dropped: string[] = [];
    const noisyMutation = Array.from({ length: 512 }, (_, index) =>
      createHash('sha256').update(String(index)).digest('hex'),
    ).join('');

    const segments = await buildReplaySegments(
      [
        replayItem({
          type: 3,
          timestamp: 3,
          data: { source: 1, text: noisyMutation },
        }),
        replayItem({ type: 3, timestamp: 4, data: { source: 1 } }),
      ],
      {
        recordingId: 'recording-01',
        firstSequence: 1,
        maxCompressedBytes: 2_000,
        maxEvents: 1,
        onDrop: (reason) => dropped.push(reason),
        targetUncompressedBytes: 256 * 1024,
      },
    );

    expect(dropped).toEqual(['segment-too-large']);
    expect(segments).toEqual([]);
  });
});
