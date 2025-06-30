import { useState, useRef } from "react";
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
  const socketRef = useRef(null);

  const handleRun = () => {
    setLogs([]);
    setLogText("");
    setResults(null);
    setLoading(true);

    const socket = new WebSocket("ws://localhost:8000/ws/agent");
    socketRef.current = socket;

    socket.onopen = () => {
      socket.send(JSON.stringify({ url, instruction }));
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "final_result") {
          setResults(data.annotated_actions);
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

    setLogs([]);
    setResults(null);
    setLoading(true);

    const socket = new WebSocket("ws://localhost:8000/ws/analyze");
    socketRef.current = socket;

    socket.onopen = () => {
      socket.send(JSON.stringify({ log_text: uploadedLog }));
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "final_result") {
          setResults(data.annotated_actions);
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
    link.download = "annotated_actions.json";
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
    link.download = "agent_log.txt";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const columns = [
    { title: "ID", dataIndex: "id", width: 60 },
    {
      title: "Goal",
      dataIndex: "goal",
      render: (text) => (
        <div style={{ whiteSpace: "normal", wordBreak: "break-word" }}>
          {text}
        </div>
      ),
    },
    {
      title: "Action Type",
      dataIndex: "action_type",
      render: (val) =>
        val ? val.charAt(0).toUpperCase() + val.slice(1) : "",
      width: 120,
    },
    {
      title: "Sensitive Data?",
      dataIndex: ["annotations", "is_sensitive_data"],
      render: (val) => (
        <span
          style={{
            display: "inline-block",
            padding: "2px 6px",
            borderRadius: "4px",
            backgroundColor: val === "True" ? "#fff5cc" : "#e6fffb",
            color: val === "True" ? "#d48806" : "#389e0d",
            fontWeight: "bold",
          }}
        >
          {val === "True" ? "Sensitive" : "Non-sensitive"}
        </span>
      ),
      width: 120,
    },
    {
      title: "Contextually Appropriate?",
      dataIndex: ["annotations", "is_contextually_appropriate"],
      render: (val) => {
        const isSafe = val === "True";
        return (
          <span
            style={{
              display: "inline-block",
              padding: "2px 6px",
              borderRadius: "4px",
              backgroundColor: isSafe ? "#e6fffb" : "#fff5cc",
              color: isSafe ? "#389e0d" : "#d48806",
              fontWeight: "bold",
            }}
          >
            {isSafe ? "Appropriate" : "Inappropriate"}
          </span>
        );
      },
      width: 140,
    },
    {
      title: "Risk Type",
      dataIndex: ["annotations", "risk_type"],
      render: (val) => (
        <span
          style={{
            display: "inline-block",
            padding: "2px 6px",
            borderRadius: "4px",
            backgroundColor: val !== "Unknown" ? "#ffe0e0" : "transparent",
            color: val !== "Unknown" ? "#c00" : "#555",
            fontWeight: val !== "Unknown" ? "bold" : "normal",
          }}
        >
          {val}
        </span>
      ),
    },
    {
      title: "Reversibility",
      dataIndex: ["annotations", "reversibility"],
      render: (val) => {
        const isSafe = val === "Instantly Reversible";
        return (
          <span
            style={{
              display: "inline-block",
              padding: "2px 6px",
              borderRadius: "4px",
              backgroundColor: isSafe ? "#e6fffb" : "#fff5cc",
              color: isSafe ? "#389e0d" : "#d48806",
              fontWeight: "bold",
            }}
          >
            {isSafe ? val : val}
          </span>
        );
      },
    },
    {
      title: "Rollback Effect",
      dataIndex: ["annotations", "rollback_effect"],
    },
    {
      title: "Impact Scope",
      dataIndex: ["annotations", "impact_scope"],
    },
  ];

  return (
    <div style={{ maxWidth: 1200, margin: "auto", padding: 24 }}>
    
      {/* 头部 Title + Button 居中 */}
      <div style={{ textAlign: "center", marginBottom: "24px" }}>
        <Title level={2}>GUI Agent Action Annotator</Title>

        <Button.Group style={{ marginBottom: 16 }}>
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
        </Button.Group>
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
              accept=".txt,.log,.json"
              showUploadList={false}
              beforeUpload={(file) => {
                const reader = new FileReader();
                reader.onload = (e) => {
                  let content = e.target.result;
                  try {
                    const json = JSON.parse(content);
                    content = JSON.stringify(json, null, 2);
                  } catch (err) {}
                  setUploadedLog(content);
                  message.success(`Log uploaded! (${file.name})`);
                };
                reader.readAsText(file);
                return false;
              }}
            >
              <Button icon={<FileTextOutlined />}>Upload Log (.txt or .json)</Button>
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
          {/* <TextArea
            rows={10}
            value={logs.join("\n")}
            readOnly
            placeholder="Realtime logs will appear here..."
            style={{ backgroundColor: "#f8f8f8", fontFamily: "monospace" }}
          /> */}
        </Spin>

        {(logText || uploadedLog) && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <Title level={4}>Full Log</Title>
              <Button
                icon={<FileTextOutlined />}
                onClick={handleDownloadLog}
              >
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
              dataSource={results.map((item, index) => ({
                key: index,
                ...item,
              }))}
              columns={columns}
              pagination={{ pageSize: 20 }}
              scroll={{ x: "max-content" }}
              onRow={(record) => ({
                onClick: () => setSelectedAction(record),
              })}
            />

            <Modal
              title={`Action #${selectedAction?.id}`}
              open={!!selectedAction}
              onCancel={() => setSelectedAction(null)}
              footer={null}
              width={600}
            >
              <pre style={{ fontSize: "0.75em", backgroundColor: "#f4f4f4", padding: "1em" }}>
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
