import os
import platform
import re
import subprocess
import sys
from pathlib import Path

try:
    from importlib.metadata import version, PackageNotFoundError  # Python 3.8+
except ImportError:
    from importlib.metadata import version, PackageNotFoundError  # 兼容旧版本

def get_pkg_version(pkg_name: str) -> str | None:
    try:
        return version(pkg_name)
    except PackageNotFoundError:
        return None

def pip_install(package: str, version: str | None = None):
    pkg = f"{package}=={version}" if version else package
    print(f"Installing {pkg} ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", pkg])

def check_version():
    grpc_version = get_pkg_version("grpcio")
    tools_version = get_pkg_version("grpcio-tools")

    print(f"Detected grpcio: {grpc_version}, grpcio-tools: {tools_version}")

    print("========== DEBUG INFO ==========")
    print(f"Python executable: {sys.executable}")
    print(f"Python version   : {platform.python_version()}")
    print(f"Platform         : {platform.system()} {platform.release()}")
    print(f"grpcio           : {grpc_version}")
    print(f"grpcio-tools     : {tools_version}")
    print("================================")

    if grpc_version and tools_version:
        if grpc_version != tools_version:
            print(f"Version mismatch: grpcio={grpc_version}, grpcio-tools={tools_version}")
            # 默认以 grpcio 版本为基准
            print(f"Syncing grpcio-tools to {grpc_version} ...")
            pip_install("grpcio-tools", grpc_version)
        else:
            print("grpcio and grpcio-tools versions are already in sync.")
    elif grpc_version and not tools_version:
        print(f"grpcio={grpc_version} is installed, grpcio-tools not found. Installing matching version...")
        pip_install("grpcio-tools", grpc_version)
    elif tools_version and not grpc_version:
        print(f"grpcio-tools={tools_version} is installed, grpcio not found. Installing matching version...")
        pip_install("grpcio", tools_version)
    else:
        print("grpcio and grpcio-tools are not installed. Installing latest version...")
        pip_install("grpcio")
        pip_install("grpcio-tools")

    print("🎉 Sync complete. Re-run your gRPC code generation / application.")


def ensure_pkg_inits(root: Path):
    # 确保生成目录里的每一层都是包，便于 import
    for p in root.rglob("*.py"):
        cur = p.parent
        while cur != root.parent:
            init_file = cur / "__init__.py"
            if not init_file.exists():
                init_file.touch()
            cur = cur.parent

def fix_imports(out: str):
    for filename in os.listdir(out):
        if filename.endswith("_pb2.pyi") or filename.endswith("_pb2_grpc.py") or filename.endswith("_pb2.py"):
            path = os.path.join(out, filename)
            with open(path, "r", encoding="utf-8") as f:
                code = f.read()

            # 修改 import xxx_pb2 => from . import xxx_pb2
            fixed_code = re.sub(
                r"^import (\w+_pb2)(.*)$",
                r"from . import \1\2",
                code,
                flags=re.MULTILINE,
            )

            if code != fixed_code:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(fixed_code)
                print(f"Fixed imports in {filename}")


def main():
    check_version()
    clean:bool=True
    mypy:bool=False
    include:list[str]=[]
    src = Path("../src/aduib_rpc/proto").resolve()
    out = Path("../src/aduib_rpc/grpc").resolve()
    out.mkdir(parents=True, exist_ok=True)

    if clean and out.exists():
        for p in out.rglob("*"):
            if p.is_file():
                p.unlink()
        for p in sorted([d for d in out.rglob("*") if d.is_dir()], reverse=True):
            try: p.rmdir()
            except OSError: pass
        out.mkdir(parents=True, exist_ok=True)

    protos = [str(p) for p in src.rglob("*.proto")]
    if not protos:
        print(f"No .proto found under {src}")
        return 1

    # 组装 protoc 命令
    cmd = [sys.executable, "-m", "grpc_tools.protoc"]
    # include 路径：默认含 src
    include_dirs = [src] + [Path(p).resolve() for p in include]
    for inc in include_dirs:
        cmd += ["-I", str(inc)]
    cmd += [
        f"--python_out={out}",
        f"--pyi_out={out}",
        f"--grpc_python_out={out}",
    ]
    if mypy:
        cmd += [f"--mypy_out={out}", f"--mypy_grpc_out={out}"]

    cmd += protos

    print("Running:", " ".join(cmd))
    res = subprocess.run(cmd)
    if res.returncode != 0:
        return res.returncode

    ensure_pkg_inits(out)
    fix_imports(out)
    print(f"Done. Generated to: {out}")
    return 0

if __name__ == "__main__":
    main()
