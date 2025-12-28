use std::net::{SocketAddr, TcpListener};
use std::io::Read;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use aduib_rpc::{AduibRpcClientBuilder, TransportKind};
use serde_json::json;

fn pick_free_port() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
    listener.local_addr().unwrap().port()
}

fn python_exe() -> std::ffi::OsString {
    std::env::var_os("ADUIB_RPC_PYTHON")
        .or_else(|| std::env::var_os("PYTHON"))
        .unwrap_or_else(|| std::ffi::OsString::from("python"))
}

fn python_has_http_server() -> bool {
    Command::new(python_exe())
        .arg("-c")
        .arg("import tests.http_server_local")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn wait_for_port_or_child_exit(child: &mut Child, addr: SocketAddr, timeout: Duration) {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if std::net::TcpStream::connect(addr).is_ok() {
            return;
        }

        if let Ok(Some(status)) = child.try_wait() {
            let mut stderr = String::new();
            if let Some(mut s) = child.stderr.take() {
                let _ = s.read_to_string(&mut stderr);
            }
            panic!("python http server exited early ({status}). stderr:\n{stderr}");
        }

        std::thread::sleep(Duration::from_millis(50));
    }

    let _ = child.kill();
    let _ = child.wait();
    let mut stderr = String::new();
    if let Some(mut s) = child.stderr.take() {
        let _ = s.read_to_string(&mut stderr);
    }
    panic!("server did not open port {addr} in time. stderr:\n{stderr}");
}

fn repo_root() -> std::path::PathBuf {
    let manifest_dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.parent())
        .expect("resolve repo root")
        .to_path_buf()
}

fn spawn_python_http_server(rest_port: u16, jsonrpc_port: u16) -> Child {
    let mut cmd = Command::new(python_exe());
    cmd.arg("-m")
        .arg("tests.http_server_local")
        .arg("--rest-port")
        .arg(rest_port.to_string())
        .arg("--jsonrpc-port")
        .arg(jsonrpc_port.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .current_dir(repo_root());

    cmd.spawn().expect("spawn python http server")
}

#[tokio::test]
async fn rest_long_task_submit_poll_and_subscribe() {
    if !python_has_http_server() {
        eprintln!("skipping REST/JSON-RPC integration tests: python module 'tests.http_server_local' (and deps) not available.");
        return;
    }

    let rest_port = pick_free_port();
    let jsonrpc_port = pick_free_port();

    let rest_addr: SocketAddr = format!("127.0.0.1:{rest_port}").parse().unwrap();
    let jsonrpc_addr: SocketAddr = format!("127.0.0.1:{jsonrpc_port}").parse().unwrap();

    let mut child = spawn_python_http_server(rest_port, jsonrpc_port);
    wait_for_port_or_child_exit(&mut child, rest_addr, Duration::from_secs(10));
    wait_for_port_or_child_exit(&mut child, jsonrpc_addr, Duration::from_secs(10));

    let client = AduibRpcClientBuilder::new(format!("http://127.0.0.1:{rest_port}"))
        .transport(TransportKind::Rest)
        .build()
        .expect("build client");

    // 1) submit
    let submit = client
        .completion(
            "task/submit",
            Some(json!({
                "target_method": "LongTaskSvc.slow_add",
                "params": {"a": 10, "b": 5, "delay_ms": 20}
            })),
            None,
        )
        .await
        .expect("submit");
    let task_id = submit.result.unwrap()["task_id"].as_str().unwrap().to_string();

    // 2) subscribe (stream) - requires SDK streaming.
    // REST server emits SSE, but SDK's completion_stream is gated by feature.
    // We call the transport stream API directly only when available.

    #[cfg(feature = "streaming")]
    {
        use futures_util::StreamExt;

        let mut saw_completed = false;
        let mut stream = client
            .completion_stream("task/subscribe", Some(json!({"task_id": task_id})), None)
            .await
            .expect("subscribe stream");

        while let Some(item) = stream.next().await {
            let resp = item.expect("stream item");
            let payload = resp.result.expect("event payload");
            if payload["event"] == "completed" {
                saw_completed = true;
                assert_eq!(payload["task"]["status"], json!("succeeded"));
                assert_eq!(payload["task"]["value"], json!(15));
                break;
            }
        }
        assert!(saw_completed, "did not receive completed event");
    }

    // 3) poll result until succeeded
    let mut ok = false;
    for _ in 0..80 {
        let res = client
            .completion("task/result", Some(json!({"task_id": task_id})), None)
            .await
            .expect("poll");

        let payload = res.result.unwrap();
        if payload["status"] == json!("succeeded") {
            assert_eq!(payload["value"], json!(15));
            ok = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    assert!(ok, "task did not finish in time");

    let _ = child.kill();
    let _ = child.wait();
}

