package aggregatecontract

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"
)

const (
	redisPassword = "rum-agg-contract-redis-0001"
	browserKey    = "browser-key-contract-0001"
	originValue   = "https://app.example.test"
	tenantID      = "core"
)

var reservedPorts = map[int]struct{}{
	4317: {}, 4318: {}, 4319: {}, 4320: {}, 4422: {}, 6379: {}, 8083: {},
	8428: {}, 9000: {}, 9001: {}, 9428: {}, 10428: {}, 10429: {}, 13135: {},
	14222: {}, 16379: {}, 18222: {}, 18223: {}, 18888: {}, 18889: {}, 19000: {},
	19001: {}, 19428: {}, 23133: {},
}

func TestAggregateContract(t *testing.T) {
	if os.Getenv("RUN_RUM_AGG_CONTRACT") != "1" {
		t.Skip("set RUN_RUM_AGG_CONTRACT=1 to run the temporary RUM aggregate containers")
	}
	stack := newStack(t)
	t.Cleanup(stack.down)
	stack.up(t)

	t.Run("labels and buckets", func(t *testing.T) {
		status := stack.post(t, stack.main, "storefront", "/checkout", "labels-1", true)
		if status != http.StatusAccepted {
			t.Fatalf("collect status = %d, gateway logs:\n%s", status, stack.logs(stack.main.name))
		}
		series := stack.waitSeries(t, `{shard="rum-agg-contract"}`, func(rows []series) bool {
			return hasName(rows, "rum_views_total") && hasName(rows, "rum_js_errors_total") && hasName(rows, "rum_web_vital_lcp_milliseconds_bucket") && hasName(rows, "rum_web_vital_cls_bucket")
		})
		assertLabels(t, series, "rum-agg-contract")
		assertRoute(t, series, "/checkout")
		assertBuckets(t, series, "rum_web_vital_lcp_milliseconds_bucket", []string{"100", "250", "500", "1000", "2500", "4000", "8000", "16000", "+Inf"})
		assertBuckets(t, series, "rum_web_vital_inp_milliseconds_bucket", []string{"50", "100", "200", "500", "1000", "2500", "+Inf"})
		assertBuckets(t, series, "rum_web_vital_cls_bucket", []string{"0.01", "0.05", "0.1", "0.25", "0.5", "1", "+Inf"})
		assertBuckets(t, series, "rum_web_vital_fcp_milliseconds_bucket", []string{"100", "250", "500", "1000", "1800", "3000", "6000", "12000", "+Inf"})
		assertBuckets(t, series, "rum_web_vital_ttfb_milliseconds_bucket", []string{"50", "100", "200", "400", "800", "1800", "4000", "+Inf"})
		logs := stack.waitLogs(t, `"rum.event.type":view "rum.view.name":"/checkout"`, 1)
		if strings.Contains(logs, "rum.aggregate.route") {
			t.Fatalf("VictoriaLogs stored the aggregate-only route field:\n%s", logs)
		}
	})

	t.Run("remote write isolation", func(t *testing.T) {
		status := stack.post(t, stack.isolate, "isolate", "/isolate", "isolate-1", false)
		if status != http.StatusAccepted {
			t.Fatalf("collect status = %d, gateway logs:\n%s", status, stack.logs(stack.isolate.name))
		}
		body := stack.waitLogs(t, `"rum.application":isolate "rum.event.type":view`, 1)
		time.Sleep(6 * time.Second)
		again := stack.queryLogs(t, `"rum.application":isolate "rum.event.type":view`)
		if strings.Count(again, "\n") != strings.Count(body, "\n") {
			t.Fatalf("VictoriaLogs duplicated events while remote write was down\nfirst:\n%s\nsecond:\n%s", body, again)
		}
	})

	t.Run("restart increase", func(t *testing.T) {
		for index := 1; index <= 3; index++ {
			status := stack.post(t, stack.main, "storefront", "/restart", fmt.Sprintf("restart-%d", index), false)
			if status != http.StatusAccepted {
				t.Fatalf("collect status = %d", status)
			}
		}
		if got := stack.waitIncrease(t, "rum-agg-contract", "/restart", 3); got != 3 {
			t.Fatalf("increase before restart = %v", got)
		}
		before := stack.readyCount(stack.main.name)
		if err := exec.Command("docker", "restart", stack.main.name).Run(); err != nil {
			t.Fatalf("restart gateway: %v\n%s", err, stack.logs(stack.main.name))
		}
		stack.waitReadyAgain(t, stack.main.name, before)
		status := stack.post(t, stack.main, "storefront", "/restart", "restart-4", false)
		if status != http.StatusAccepted {
			t.Fatalf("collect after restart status = %d\n%s", status, stack.logs(stack.main.name))
		}
		if got := stack.waitIncrease(t, "rum-agg-contract", "/restart", 4); got != 4 {
			t.Fatalf("increase after restart = %v", got)
		}
	})

	t.Run("max streams drop metric", func(t *testing.T) {
		status := stack.post(t, stack.capped, "storefront", "/capped", "capped-1", true)
		if status != http.StatusAccepted {
			t.Fatalf("collect status = %d\n%s", status, stack.logs(stack.capped.name))
		}
		body := stack.waitMetrics(t, stack.capped.metricsPort, func(text string) bool {
			return strings.Contains(text, "otelcol_deltatocumulative_datapoints") && strings.Contains(text, `error="limit"`)
		})
		if !strings.Contains(body, "otelcol_deltatocumulative_datapoints") {
			t.Fatalf("dropped samples were not counted:\n%s", tail(body, 80))
		}
	})
}

type series struct {
	Metric map[string]string `json:"metric"`
	Value  []any             `json:"value"`
}

type gateway struct {
	name        string
	collectPort int
	metricsPort int
}

type stack struct {
	id       string
	network  string
	redis    string
	logsName string
	vmName   string
	logsPort int
	vmPort   int
	main     gateway
	isolate  gateway
	capped   gateway
}

func newStack(t *testing.T) *stack {
	t.Helper()
	id := strconv.Itoa(os.Getpid())
	return &stack{
		id:       id,
		network:  "rum-agg-verify-" + id,
		redis:    "rum-agg-verify-" + id + "-redis",
		logsName: "rum-agg-verify-" + id + "-vl",
		vmName:   "rum-agg-verify-" + id + "-vm",
		main:     gateway{name: "rum-agg-verify-" + id + "-gw"},
		isolate:  gateway{name: "rum-agg-verify-" + id + "-iso"},
		capped:   gateway{name: "rum-agg-verify-" + id + "-cap"},
	}
}

func (stack *stack) up(t *testing.T) {
	t.Helper()
	image := envOr("RUM_AGG_VERIFY_IMAGE", "bklite/rum-collector:0.1.0-bklite.3")
	if err := exec.Command("docker", "image", "inspect", image).Run(); err != nil {
		t.Fatalf("image %s is not present; build it before the contract", image)
	}
	if err := exec.Command("docker", "network", "create", stack.network).Run(); err != nil {
		t.Fatalf("create network: %v", err)
	}
	stack.run(t, "redis", stack.redis, envOr("RUM_AGG_REDIS_IMAGE", "redis:7.4-alpine"), nil, nil,
		"redis-server", "--requirepass", redisPassword, "--save", "", "--appendonly", "no")
	stack.logsPort = freePort(t)
	stack.run(t, "vl", stack.logsName, envOr("RUM_AGG_VL_IMAGE", "victoriametrics/victoria-logs:v1.38.0"),
		[]string{fmt.Sprintf("127.0.0.1:%d:9428", stack.logsPort)}, nil,
		"-storageDataPath=/victoria-logs-data", "-httpListenAddr=:9428")
	stack.vmPort = freePort(t)
	stack.run(t, "vm", stack.vmName, envOr("RUM_AGG_VM_IMAGE", "victoriametrics/victoria-metrics:v1.106.1"),
		[]string{fmt.Sprintf("127.0.0.1:%d:8428", stack.vmPort)}, nil,
		"-storageDataPath=/victoria-metrics-data", "-httpListenAddr=:8428", "-retentionPeriod=35d")
	stack.waitHTTP(t, fmt.Sprintf("http://127.0.0.1:%d/health", stack.logsPort))
	stack.waitHTTP(t, fmt.Sprintf("http://127.0.0.1:%d/health", stack.vmPort))
	stack.waitRedis(t)
	stack.seed(t)

	stack.main.collectPort, stack.main.metricsPort = freePort(t), freePort(t)
	stack.isolate.collectPort, stack.isolate.metricsPort = freePort(t), freePort(t)
	stack.capped.collectPort, stack.capped.metricsPort = freePort(t), freePort(t)
	writeURL := fmt.Sprintf("http://%s:8428/api/v1/write", stack.vmName)
	stack.startGateway(t, stack.main, image, "rum-agg-contract", writeURL, "420000")
	stack.startGateway(t, stack.isolate, image, "rum-agg-isolate", "http://127.0.0.1:9/api/v1/write", "420000")
	stack.startGateway(t, stack.capped, image, "rum-agg-limit", writeURL, "2")
	stack.waitReady(t, stack.main.name)
	stack.waitReady(t, stack.isolate.name)
	stack.waitReady(t, stack.capped.name)
}

func (stack *stack) startGateway(t *testing.T, gw gateway, image, shard, writeURL, maxStreams string) {
	t.Helper()
	redisURL := fmt.Sprintf("redis://:%s@%s:6379", redisPassword, stack.redis)
	env := []string{
		"RUM_TENANT_ID=" + tenantID,
		"RUM_IDENTITY_HMAC_CURRENT=dev-bklite-rum-hmac-secret-key-32b",
		"RUM_IDENTITY_HMAC_CURRENT_VERSION=v1",
		"RUM_IDENTITY_HMAC_PREVIOUS=",
		"RUM_IDENTITY_HMAC_PREVIOUS_VERSION=",
		"RUM_ADMISSION_REDIS_URL=" + redisURL + "/0",
		"RUM_SESSION_REDIS_URL=" + redisURL + "/1",
		"RUM_REPLAY_REDIS_URL=" + redisURL + "/2",
		"RUM_VICTORIA_LOGS_ENDPOINT=http://" + stack.logsName + ":9428",
		"RUM_VICTORIA_TRACES_ENDPOINT=http://127.0.0.1:1",
		"RUM_MINIO_ENDPOINT=127.0.0.1:1",
		"RUM_MINIO_ACCESS_KEY=rumminio",
		"RUM_MINIO_SECRET_KEY=rum-minio-contract-password",
		"RUM_MINIO_SECURE=false",
		"RUM_QUEUE_DIR=/tmp/bklite-rum-queue",
		"AGG_VICTORIAMETRICS_WRITE_URL=" + writeURL,
		"RUM_AGG_SHARD=" + shard,
		"RUM_AGG_BATCH_TIMEOUT=1s",
		"RUM_AGG_MAX_STREAMS=" + maxStreams,
	}
	ports := []string{
		fmt.Sprintf("127.0.0.1:%d:4319", gw.collectPort),
		fmt.Sprintf("127.0.0.1:%d:8888", gw.metricsPort),
	}
	stack.run(t, "gw", gw.name, image, ports, env, "--config=/etc/bklite-rum/rum.gateway.dev.yaml")
}

func (stack *stack) down() {
	for _, name := range []string{stack.main.name, stack.isolate.name, stack.capped.name, stack.vmName, stack.logsName, stack.redis} {
		_ = exec.Command("docker", "rm", "-f", name).Run()
	}
	_ = exec.Command("docker", "network", "rm", stack.network).Run()
}

func (stack *stack) run(t *testing.T, kind, name, image string, ports, env []string, args ...string) {
	t.Helper()
	command := []string{"run", "-d", "--name", name, "--network", stack.network, "--label", "bk-lite-rum-agg-verify=1"}
	for _, port := range ports {
		command = append(command, "-p", port)
	}
	for _, item := range env {
		command = append(command, "-e", item)
	}
	if kind == "gw" {
		command = append(command,
			"--tmpfs", "/tmp:rw,mode=1777",
			"-v", gatewayConfig(t)+":/etc/bklite-rum/rum.gateway.dev.yaml:ro",
			"--entrypoint", "/usr/local/bin/bklite-rum-gateway",
		)
	}
	command = append(command, image)
	command = append(command, args...)
	output, err := exec.Command("docker", command...).CombinedOutput()
	if err != nil {
		t.Fatalf("docker run %s: %v\n%s", name, err, output)
	}
}

func (stack *stack) seed(t *testing.T) {
	t.Helper()
	sum := sha256.Sum256([]byte(browserKey))
	digest := hex.EncodeToString(sum[:])
	for _, application := range []string{"storefront", "isolate"} {
		key := "ops:rum:v2:app:" + application
		stack.redisCLI(t, "HSET", key,
			"tenant_id", tenantID,
			"enabled", "1",
			"revision", "1",
			"requests_per_minute", "1000000",
			"compressed_bytes_per_minute", "1000000000",
			"decompressed_bytes_per_minute", "1000000000",
			"events_per_minute", "1000000",
		)
		stack.redisCLI(t, "SADD", key+":keys", digest)
		stack.redisCLI(t, "SADD", key+":origins", originValue)
	}
}

func (stack *stack) redisCLI(t *testing.T, args ...string) {
	t.Helper()
	command := append([]string{"exec", stack.redis, "redis-cli", "-a", redisPassword, "-n", "0"}, args...)
	var output []byte
	var err error
	deadline := time.Now().Add(30 * time.Second)
	for {
		output, err = exec.Command("docker", command...).CombinedOutput()
		if err == nil && !strings.Contains(string(output), "LOADING") {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("redis-cli %v: %v\n%s", args, err, output)
		}
		time.Sleep(time.Second)
	}
}

func (stack *stack) waitRedis(t *testing.T) {
	t.Helper()
	stack.redisCLI(t, "PING")
}

func (stack *stack) post(t *testing.T, gw gateway, application, route, batchID string, withVitals bool) int {
	t.Helper()
	body := payload(application, route, withVitals)
	client := http.Client{Timeout: 10 * time.Second}
	deadline := time.Now().Add(20 * time.Second)
	var response *http.Response
	for {
		request, err := http.NewRequest(http.MethodPost, fmt.Sprintf("http://127.0.0.1:%d/rum/v1/collect", gw.collectPort), strings.NewReader(body))
		if err != nil {
			t.Fatal(err)
		}
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("X-API-Key", browserKey)
		request.Header.Set("X-RUM-Application", application)
		request.Header.Set("X-RUM-Batch-Id", batchID)
		request.Header.Set("Origin", originValue)
		response, err = client.Do(request)
		if err == nil {
			break
		}
		if time.Now().After(deadline) {
			ports, _ := exec.Command("docker", "port", gw.name).CombinedOutput()
			t.Fatalf("post collect: %v\nports:\n%s\n%s", err, ports, stack.logs(gw.name))
		}
		time.Sleep(time.Second)
	}
	defer response.Body.Close()
	responseBody, _ := io.ReadAll(response.Body)
	if response.StatusCode != http.StatusAccepted {
		t.Logf("collect response %d: %s", response.StatusCode, responseBody)
	}
	return response.StatusCode
}

func (stack *stack) waitSeries(t *testing.T, query string, ready func([]series) bool) []series {
	t.Helper()
	var last []series
	deadline := time.Now().Add(45 * time.Second)
	for {
		last = stack.querySeries(t, query)
		if ready(last) {
			return last
		}
		if time.Now().After(deadline) {
			t.Fatalf("series %s not ready; names=%v\nmain logs:\n%s", query, namesOf(last), tail(stack.logs(stack.main.name), 80))
		}
		time.Sleep(time.Second)
	}
}

func (stack *stack) waitIncrease(t *testing.T, shard, route string, want float64) float64 {
	t.Helper()
	query := fmt.Sprintf(`sum(increase(rum_views_total{shard=%q,rum_aggregate_route=%q}[5m]))`, shard, route)
	var got float64
	deadline := time.Now().Add(60 * time.Second)
	for {
		rows := stack.querySeries(t, query)
		if len(rows) > 0 && len(rows[0].Value) == 2 {
			got, _ = strconv.ParseFloat(fmt.Sprint(rows[0].Value[1]), 64)
			if got == want {
				return got
			}
		}
		if time.Now().After(deadline) {
			return got
		}
		time.Sleep(time.Second)
	}
}

func (stack *stack) querySeries(t *testing.T, query string) []series {
	t.Helper()
	endpoint := fmt.Sprintf("http://127.0.0.1:%d/api/v1/query?query=%s", stack.vmPort, url.QueryEscape(query))
	response, err := http.Get(endpoint)
	if err != nil {
		return nil
	}
	defer response.Body.Close()
	var decoded struct {
		Data struct {
			Result []series `json:"result"`
		} `json:"data"`
	}
	if err := json.NewDecoder(response.Body).Decode(&decoded); err != nil {
		return nil
	}
	return decoded.Data.Result
}

func (stack *stack) waitLogs(t *testing.T, query string, count int) string {
	t.Helper()
	deadline := time.Now().Add(45 * time.Second)
	var body string
	for {
		body = stack.queryLogs(t, query)
		if strings.Count(strings.TrimSpace(body), "\n")+boolToInt(strings.TrimSpace(body) != "") >= count && strings.TrimSpace(body) != "" {
			return body
		}
		if time.Now().After(deadline) {
			t.Fatalf("logs %s not ready:\n%s\nmain logs:\n%s", query, body, tail(stack.logs(stack.main.name), 60))
		}
		time.Sleep(time.Second)
	}
}

func (stack *stack) queryLogs(t *testing.T, query string) string {
	t.Helper()
	endpoint := fmt.Sprintf("http://127.0.0.1:%d/select/logsql/query?query=%s", stack.logsPort, url.QueryEscape(query))
	response, err := http.Get(endpoint)
	if err != nil {
		return ""
	}
	defer response.Body.Close()
	body, _ := io.ReadAll(response.Body)
	return string(body)
}

func (stack *stack) waitMetrics(t *testing.T, port int, ready func(string) bool) string {
	t.Helper()
	deadline := time.Now().Add(45 * time.Second)
	var body string
	for {
		response, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/metrics", port))
		if err == nil {
			raw, _ := io.ReadAll(response.Body)
			response.Body.Close()
			body = string(raw)
			if ready(body) {
				return body
			}
		}
		if time.Now().After(deadline) {
			return body
		}
		time.Sleep(time.Second)
	}
}

func (stack *stack) waitHTTP(t *testing.T, endpoint string) {
	t.Helper()
	deadline := time.Now().Add(60 * time.Second)
	for {
		response, err := http.Get(endpoint)
		if err == nil {
			response.Body.Close()
			if response.StatusCode < 500 {
				return
			}
		}
		if time.Now().After(deadline) {
			t.Fatalf("timeout waiting for %s: %v", endpoint, err)
		}
		time.Sleep(time.Second)
	}
}

func (stack *stack) waitReady(t *testing.T, name string) {
	t.Helper()
	stack.waitReadyAgain(t, name, 0)
}

func (stack *stack) waitReadyAgain(t *testing.T, name string, previous int) {
	t.Helper()
	deadline := time.Now().Add(90 * time.Second)
	for {
		if stack.readyCount(name) > previous {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("gateway %s did not become ready\n%s", name, stack.logs(name))
		}
		time.Sleep(time.Second)
	}
}

func (stack *stack) readyCount(name string) int {
	return strings.Count(stack.logs(name), "Everything is ready")
}

func (stack *stack) logs(name string) string {
	output, _ := exec.Command("docker", "logs", "--tail", "120", name).CombinedOutput()
	return string(output)
}

func payload(application, route string, withVitals bool) string {
	now := time.Now().UTC().Format(time.RFC3339Nano)
	vitals := ""
	if withVitals {
		vitals = fmt.Sprintf(`,"exceptions":[{"type":"TypeError","value":"failed","timestamp":%q}],"measurements":[{"type":"web-vitals","values":{"lcp":1200,"inp":80,"cls":0.02,"fcp":900,"ttfb":70},"timestamp":%q}]`, now, now)
	}
	return fmt.Sprintf(`{"meta":{"app":{"name":%q,"environment":"prod"},"session":{"id":"session-secret-should-not-label"},"user":{"id":"user-secret-should-not-label"},"page":{"id":"page-1","url":"https://shop.example/checkout?token=secret"},"view":{"name":%q},"browser":{"userAgent":"Mozilla/5.0 Chrome/126.0.0.0"}},"events":[{"name":"view_changed","timestamp":%q}]%s}`, application, route, now, vitals)
}

func assertLabels(t *testing.T, rows []series, shard string) {
	t.Helper()
	allowed := map[string]struct{}{
		"__name__": {}, "shard": {}, "tenant_id": {},
		"rum_traffic_class": {}, "rum_application": {}, "rum_environment": {},
		"rum_aggregate_route": {}, "signal_to_metrics_service_instance_id": {}, "le": {},
	}
	for _, row := range rows {
		for key, value := range row.Metric {
			if _, ok := allowed[key]; !ok {
				t.Fatalf("unexpected label %s=%s in %#v", key, value, row.Metric)
			}
			if strings.Contains(value, "secret") || strings.Contains(value, "token=") {
				t.Fatalf("label %s leaked a forbidden value %s", key, value)
			}
		}
		for _, key := range []string{"shard", "signal_to_metrics_service_instance_id"} {
			if value, ok := row.Metric[key]; ok && value != shard {
				t.Fatalf("%s = %s, want shard %s", key, value, shard)
			}
		}
		if row.Metric["__name__"] == "target_info" {
			t.Fatalf("target_info was written: %#v", row.Metric)
		}
	}
}

func assertRoute(t *testing.T, rows []series, route string) {
	t.Helper()
	for _, row := range rows {
		if row.Metric["__name__"] == "rum_views_total" && row.Metric["rum_aggregate_route"] != route {
			t.Fatalf("route = %s, want %s", row.Metric["rum_aggregate_route"], route)
		}
	}
}

func assertBuckets(t *testing.T, rows []series, name string, want []string) {
	t.Helper()
	got := map[string]struct{}{}
	for _, row := range rows {
		if row.Metric["__name__"] == name {
			got[normalizeLe(row.Metric["le"])] = struct{}{}
		}
	}
	if len(got) == 0 {
		t.Fatalf("missing %s; names=%v", name, namesOf(rows))
	}
	for _, le := range want {
		if _, ok := got[normalizeLe(le)]; !ok {
			t.Fatalf("%s missing le %s; got %v", name, le, keys(got))
		}
	}
}

func hasName(rows []series, name string) bool {
	for _, row := range rows {
		if row.Metric["__name__"] == name {
			return true
		}
	}
	return false
}

func namesOf(rows []series) []string {
	seen := map[string]struct{}{}
	for _, row := range rows {
		seen[row.Metric["__name__"]] = struct{}{}
	}
	return keys(seen)
}

func keys(values map[string]struct{}) []string {
	out := make([]string, 0, len(values))
	for key := range values {
		out = append(out, key)
	}
	sort.Strings(out)
	return out
}

func normalizeLe(value string) string {
	if value == "+Inf" {
		return value
	}
	number, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return value
	}
	return strconv.FormatFloat(number, 'f', -1, 64)
}

func gatewayConfig(t *testing.T) string {
	t.Helper()
	path, err := filepath.Abs(filepath.Join("..", "..", "..", "otel", "rum.gateway.dev.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	return path
}

func freePort(t *testing.T) int {
	t.Helper()
	for {
		listener, err := net.Listen("tcp", "127.0.0.1:0")
		if err != nil {
			t.Fatal(err)
		}
		port := listener.Addr().(*net.TCPAddr).Port
		_ = listener.Close()
		if _, reserved := reservedPorts[port]; !reserved {
			return port
		}
	}
}

func envOr(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func boolToInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

func tail(text string, lines int) string {
	parts := strings.Split(text, "\n")
	if len(parts) <= lines {
		return text
	}
	return strings.Join(parts[len(parts)-lines:], "\n")
}
