// @vitest-environment jsdom

import React from "react";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ScreenRenderContext } from "@/app/ops-analysis/types/dashBoard";

const sceneController = vi.hoisted(() => ({
  resetView: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
}));
const sceneCallbacks = vi.hoisted(() => ({
  current: null as { onFirstRender?: () => void } | null,
  history: [] as Array<{ onFirstRender?: () => void }>,
}));
const translate = vi.hoisted(() => vi.fn((key: string) => key));
const createRoom3DSceneMock = vi.hoisted(() =>
  vi.fn(
    (
      _mountNode: HTMLDivElement,
      _roomData: unknown,
      callbacks: { onFirstRender?: () => void },
    ) => {
      sceneCallbacks.current = callbacks;
      sceneCallbacks.history.push(callbacks);
      return sceneController;
    },
  ),
);

vi.mock("../room3DScene", () => ({
  createRoom3DScene: createRoom3DSceneMock,
}));

vi.mock("@/utils/i18n", () => ({
  useTranslation: () => ({ t: translate }),
}));

import Room3D from "../index";

const roomData = {
  room: { id: "room-1", name: "Room 1" },
  racks: [{ rack_id: "rack-1", rack_name: "Rack 1", row: 1, col: 1 }],
};

const buildScreenRenderContext = (
  fitScale: number,
): ScreenRenderContext => ({
  enabled: true,
  fitScale,
  screenDensity: 1,
  screenUiScale: 1,
  widgetDensity: 1,
  widgetUiScale: 1,
});

describe("Room3D screen resize", () => {
  beforeEach(() => {
    sceneController.resetView.mockClear();
    sceneController.resize.mockClear();
    sceneController.dispose.mockClear();
    createRoom3DSceneMock.mockClear();
    sceneCallbacks.current = null;
    sceneCallbacks.history.length = 0;
  });

  afterEach(cleanup);

  it("resizes the existing scene when the screen fit scale changes", async () => {
    const view = render(
      <Room3D
        rawData={roomData}
        screenRenderContext={buildScreenRenderContext(0.5)}
      />,
    );
    await waitFor(() => expect(createRoom3DSceneMock).toHaveBeenCalled());
    sceneController.resize.mockClear();

    view.rerender(
      <Room3D
        rawData={roomData}
        screenRenderContext={buildScreenRenderContext(0.75)}
      />,
    );

    expect(sceneController.resize).toHaveBeenCalledTimes(1);
  });

  it("reports ready only after the scene has rendered its first frame", async () => {
    const onReady = vi.fn();
    render(<Room3D rawData={roomData} onReady={onReady} />);
    await waitFor(() => expect(createRoom3DSceneMock).toHaveBeenCalled());

    expect(onReady).not.toHaveBeenCalled();

    await act(async () => {
      sceneCallbacks.current?.onFirstRender?.();
    });

    await waitFor(() => expect(onReady).toHaveBeenCalledWith(true));
  });

  it("creates the scene after loading and then waits for its first frame", async () => {
    const onReady = vi.fn();
    const view = render(
      <Room3D rawData={roomData} loading onReady={onReady} />,
    );
    expect(createRoom3DSceneMock).not.toHaveBeenCalled();
    expect(onReady).not.toHaveBeenCalled();

    view.rerender(
      <Room3D rawData={roomData} loading={false} onReady={onReady} />,
    );
    await waitFor(() => expect(createRoom3DSceneMock).toHaveBeenCalled());
    expect(onReady).not.toHaveBeenCalled();

    await act(async () => {
      sceneCallbacks.current?.onFirstRender?.();
    });
    await waitFor(() => expect(onReady).toHaveBeenCalledWith(true));
  });

  it("keeps the existing terminal readiness behavior for an error state", async () => {
    const onReady = vi.fn();
    render(
      <Room3D
        rawData={roomData}
        errorMessage="failed to render"
        onReady={onReady}
      />,
    );

    expect(createRoom3DSceneMock).not.toHaveBeenCalled();
    await waitFor(() => expect(onReady).toHaveBeenCalledWith(true));
  });

  it("ignores a stale first-render callback after room data changes", async () => {
    const onReady = vi.fn();
    const view = render(<Room3D rawData={roomData} onReady={onReady} />);
    await waitFor(() => expect(sceneCallbacks.history).toHaveLength(1));
    const staleCallback = sceneCallbacks.history[0];

    view.rerender(
      <Room3D
        rawData={{
          room: { id: "room-2", name: "Room 2" },
          racks: [
            { rack_id: "rack-2", rack_name: "Rack 2", row: 1, col: 1 },
          ],
        }}
        onReady={onReady}
      />,
    );
    await waitFor(() => expect(sceneCallbacks.history).toHaveLength(2));

    await act(async () => {
      staleCallback?.onFirstRender?.();
    });
    expect(onReady).not.toHaveBeenCalled();

    await act(async () => {
      sceneCallbacks.current?.onFirstRender?.();
    });
    await waitFor(() => expect(onReady).toHaveBeenCalledWith(true));
  });
});
