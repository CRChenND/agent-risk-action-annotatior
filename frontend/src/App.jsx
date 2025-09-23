import { useState, useRef, useEffect } from "react"; // FIX: 加 useEffect
import {
  Input,
  Button,
  Spin,
  Typography,
  Table,
  Space,
  message,
  Upload,
  Modal,
} from "antd";
import {
  DownloadOutlined,
  PlayCircleOutlined,
  FileTextOutlined,
  CloudUploadOutlined,
} from "@ant-design/icons";

const { TextArea } = Input;
const { Title } = Typography;

function App() {
  const [mode, setMode] = useState("exploration");
  const [url, setUrl] = useState("");
  const [instruction, setInstruction] = useState("");
  const [logs, setLogs] = useState([]);
  const [logText, setLogText] = useState("");
  const [uploadedLog, setUploadedLog] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedAction, setSelectedAction] = useState(null);
  const [selectedIndex, setSelectedIndex] = useState(null); // FIX: 记录索引
  const [maxSteps, setMaxSteps] = useState(""); // FIX: 移到组件内
  const socketRef = useRef(null);

  // FIX: 组件卸载时关闭 socket
  useEffect(() => {
    return () => {
      try {
        socketRef.current?.close();
      } catch {}
    };
  }, []);

  // FIX: 动态计算 WS 地址（本地开发也能覆盖）
  const wsBase = (() => {
    const isLocal = location.hostname === "localhost" || location.hostname === "127.0.0.1";
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const host = isLocal ? "localhost:8000" : location.host;
    return `${proto}://${host}`;
  })();

  const closeExistingSocket = () => {
    try {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.close();
      }
    } catch {}
  };

  const handleRun = () => {
    closeExistingSocket(); // FIX
    setLogs([]);
    setLogText("");
    setResults(null);
    setLoading(true);

    const socket = new WebSocket(`${wsBase}/ws/agent`); // FIX
    socketRef.current = socket;

    socket.onopen = () => {
      const payload = { url, instruction, max_steps: maxSteps || 10 };
      socket.send(JSON.stringify(payload));
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "final_result") {
          setResults(data.annotated_combined);
          setLoading(false);
          message.success("✅ Agent finished successfully");
        } else if (data.type === "agent_log_text") {
          setLogText(data.log_text);
        } else if (data.type === "error") {
          setLogs((prev) => [...prev, `❌ Error: ${data.message}`]);
          setLoading(false);
        }
      } catch {
        setLogs((prev) => [...prev, event.data]);
      }
    };

    socket.onerror = () => {
      setLogs((prev) => [...prev, "❌ WebSocket error"]);
      setLoading(false);
    };

    socket.onclose = () => {
      setLogs((prev) => [...prev, "✅ WebSocket closed"]);
      setLoading(false);
    };
  };

  const handleAnalyze = () => {
    if (!uploadedLog) {
      message.error("Please upload a log first.");
      return;
    }

    closeExistingSocket(); // FIX
    setLogs([]);
    setResults(null);
    setLoading(true);

    const socket = new WebSocket(`${wsBase}/ws/analyze`); // FIX
    socketRef.current = socket;

    socket.onopen = () => {
      socket.send(JSON.stringify({ log_text: uploadedLog }));
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "final_result") {
          setResults(data.annotated_combined);
          setLoading(false);
          message.success("✅ Analysis finished successfully");
        } else if (data.type === "error") {
          setLogs((prev) => [...prev, `❌ Error: ${data.message}`]);
          setLoading(false);
        }
      } catch {
        setLogs((prev) => [...prev, event.data]);
      }
    };

    socket.onerror = () => {
      setLogs((prev) => [...prev, "❌ WebSocket error"]);
      setLoading(false);
    };

    socket.onclose = () => {
      setLogs((prev) => [...prev, "✅ WebSocket closed"]);
      setLoading(false);
    };
  };

  const handleDownloadJSON = () => {
    if (!results) return;
    const blob = new Blob([JSON.stringify(results, null, 2)], {
      type: "application/json",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "annotated_combined.json";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleDownloadLog = () => {
    const text = mode === "exploration" ? logText : uploadedLog;
    if (!text) return;
    const blob = new Blob([text], { type: "text/plain" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = mode === "exploration" ? "agent_log.jsonl" : "uploaded_log.txt"; // FIX: 名称更贴切
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const summarizeInteracted = (ie) => {
    if (!ie) return "";
    if (typeof ie === "string") return ie.slice(0, 120);
    return (
      ie?.attributes?.id ||
      ie?.node_name ||
      (typeof ie?.x_path === "string" ? ie.x_path.slice(0, 80) : "") ||
      JSON.stringify(ie).slice(0, 120)
    );
  };

  const columns = [
    { title: "ID", key: "id", width: 60, render: (_, __, index) => index + 1 },
    {
      title: "Kind",
      dataIndex: "kind",
      width: 110,
      render: (k) => (
        <span
          style={{
            padding: "2px 6px",
            borderRadius: 4,
            background: k === "executed" ? "#e6f7ff" : "#f9f0ff",
            color: k === "executed" ? "#096dd9" : "#722ed1",
            fontWeight: 600,
          }}
        >
          {k}
        </span>
      ),
    },
    {
      title: "Goal",
      key: "goal",
      render: (_, rec) => (
        <div style={{ whiteSpace: "normal", wordBreak: "break-word" }}>
          {rec.next_goal || rec.thinking || rec.memory || ""}
        </div>
      ),
    },
    {
      title: "Action Type",
      dataIndex: ["action", "type"],
      width: 130,
      render: (val) => (val ? val.charAt(0).toUpperCase() + val.slice(1) : ""),
    },
    {
      title: "Action Name",
      dataIndex: ["action", "name"],
      width: 220,
    },
    {
      title: "Element",
      dataIndex: ["action", "interacted_element"],
      width: 260,
      render: (ie) => (
        <span title={typeof ie === "string" ? ie : JSON.stringify(ie)}>
          {summarizeInteracted(ie)}
        </span>
      ),
    },
    {
      title: "Sensitive Data?",
      dataIndex: ["annotations", "is_sensitive_data"],
      width: 140,
      render: (val) => (
        <span
          style={{
            display: "inline-block",
            padding: "2px 6px",
            borderRadius: 4,
            backgroundColor: val === "True" ? "#fff5cc" : "#e6fffb",
            color: val === "True" ? "#d48806" : "#389e0d",
            fontWeight: 700,
          }}
        >
          {val === "True" ? "Sensitive" : "Non-sensitive"}
        </span>
      ),
    },
    {
      title: "Contextually Appropriate?",
      dataIndex: ["annotations", "is_contextually_appropriate"],
      width: 180,
      render: (val) => {
        const isSafe = val === "True";
        return (
          <span
            style={{
              display: "inline-block",
              padding: "2px 6px",
              borderRadius: 4,
              backgroundColor: isSafe ? "#e6fffb" : "#fff5cc",
              color: isSafe ? "#389e0d" : "#d48806",
              fontWeight: 700,
            }}
          >
            {isSafe ? "Appropriate" : "Inappropriate"}
          </span>
        );
      },
    },
    {
      title: "Risk Type",
      dataIndex: ["annotations", "risk_type"],
      render: (val) => (
        <span
          style={{
            display: "inline-block",
            padding: "2px 6px",
            borderRadius: 4,
            backgroundColor: val && val !== "Unknown" ? "#ffe0e0" : "transparent",
            color: val && val !== "Unknown" ? "#c00" : "#555",
            fontWeight: val && val !== "Unknown" ? 700 : 400,
          }}
        >
          {val}
        </span>
      ),
    },
    {
      title: "Reversibility",
      dataIndex: ["annotations", "reversibility"],
      width: 200,
    },
    {
      title: "Rollback Effect",
      dataIndex: ["annotations", "rollback_effect"],
      width: 220,
    },
    {
      title: "Impact Scope",
      dataIndex: ["annotations", "impact_scope"],
      width: 200,
    },
  ];

  const clamp = (n, min, max) => Math.max(min, Math.min(max, n));

  return (
    <div style={{ maxWidth: 1200, margin: "auto", padding: 24 }}>
      <div style={{ textAlign: "center", marginBottom: "24px" }}>
        <Title level={2}>GUI Agent Action Annotator</Title>

        <Space.Compact style={{ marginBottom: 16 }}>
          <Button
            type={mode === "exploration" ? "primary" : "default"}
            onClick={() => setMode("exploration")}
          >
            Exploration Mode
          </Button>
          <Button
            type={mode === "analysis" ? "primary" : "default"}
            onClick={() => setMode("analysis")}
          >
            Analysis Mode
          </Button>
        </Space.Compact>
      </div>

      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        {mode === "exploration" && (
          <>
            <Input
              placeholder="Enter URL, e.g., http://example.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <Input
              placeholder="Enter instruction, e.g., Log in to the site"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
            />
            <Input
              type="number"
              min={1}
              max={50}
              value={maxSteps}
              onChange={(e) => {
                const v = Number(e.target.value);
                setMaxSteps(Number.isFinite(v) ? clamp(v, 1, 50) : "");
              }}
              placeholder="Max steps (default 10)"
            />
            <Button
              icon={<PlayCircleOutlined />}
              type="primary"
              loading={loading}
              onClick={handleRun}
            >
              Run Agent
            </Button>
          </>
        )}

        {mode === "analysis" && (
          <>
            <Upload
              accept=".txt,.log,.json,.jsonl" // FIX: 支持 jsonl
              showUploadList={false}
              beforeUpload={(file) => {
                const reader = new FileReader();
                reader.onload = (e) => {
                  let content = e.target.result;
                  try {
                    const json = JSON.parse(content);
                    content = JSON.stringify(json, null, 2);
                  } catch (err) {}
                  setUploadedLog(String(content || ""));
                  message.success(`Log uploaded! (${file.name})`);
                };
                reader.readAsText(file);
                return false;
              }}
            >
              <Button icon={<FileTextOutlined />}>Upload Log (.txt/.json/.jsonl)</Button>
            </Upload>

            <Button
              icon={<CloudUploadOutlined />}
              type="primary"
              loading={loading}
              disabled={!uploadedLog}
              onClick={handleAnalyze}
            >
              Analyze Log
            </Button>
          </>
        )}

        <Spin spinning={loading}>
          <TextArea
            rows={10}
            value={logs.join("\n")}
            readOnly
            placeholder="Realtime logs will appear here..."
            style={{ backgroundColor: "#f8f8f8", fontFamily: "monospace" }}
          />
        </Spin>

        {(logText || uploadedLog) && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <Title level={4}>Full Log</Title>
              <Button icon={<FileTextOutlined />} onClick={handleDownloadLog}>
                Export Log
              </Button>
            </div>
            <TextArea
              rows={10}
              value={mode === "exploration" ? logText : uploadedLog}
              readOnly
              style={{ backgroundColor: "#f4f4f4", fontFamily: "monospace" }}
            />
          </>
        )}

        {results && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <Title level={4}>Annotated Actions</Title>
              <Button icon={<DownloadOutlined />} onClick={handleDownloadJSON}>
                Export JSON
              </Button>
            </div>
            <Table
              dataSource={results.map((item, index) => ({ key: index, ...item }))}
              columns={columns}
              pagination={{ pageSize: 20 }}
              scroll={{ x: "max-content" }}
              onRow={(_, idx) => ({
                onClick: () => {
                  setSelectedIndex(idx); // FIX: 存索引
                  setSelectedAction(results[idx]);
                },
              })}
            />

            <Modal
              title={
                selectedAction
                  ? `Record #${(selectedIndex ?? 0) + 1} (${selectedAction.kind})`
                  : "Record"
              }
              open={!!selectedAction}
              onCancel={() => {
                setSelectedAction(null);
                setSelectedIndex(null);
              }}
              footer={null}
              width={680}
            >
              <pre
                style={{
                  fontSize: "0.75em",
                  backgroundColor: "#f4f4f4",
                  padding: "1em",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {selectedAction ? JSON.stringify(selectedAction, null, 2) : ""}
              </pre>
            </Modal>
          </>
        )}
      </Space>
    </div>
  );
}

export default App;
