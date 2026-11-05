#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/.model"
mkdir -p "$DEST"
case "$(uname -s):$(uname -m)" in
 Linux:x86_64|Linux:amd64) PLATFORM="ubuntu-x64"; ASHA="cf07c1c112d709bd67e522017471de57ed0ec8bea031d732c5422351c07f65ac";;
 Darwin:arm64) PLATFORM="macos-arm64"; ASHA="dbed55493d72bc1ba2babc8770d669c2289b5bc4ee9fb2a4dfc158d45b7d13fd";;
 Darwin:x86_64) PLATFORM="macos-x64"; ASHA="cab28238d78158109b48deb27b05d50e0dcef56275d2e76da9ca8281526c7532";;
 *) echo "Automatic model runtime download supports Linux x86_64 and macOS arm64/x64." >&2; exit 1;;
esac
MODEL="$DEST/qwen3-0.6b-q4_k_m.gguf"
MSHA="ac2d97712095a558e31573f62f466a3f9d93990898b0ec79d7c974c1780d524a"
sha() { python3 - "$1" <<'PY'
import hashlib,sys
h=hashlib.sha256()
with open(sys.argv[1],'rb') as f:
 for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
print(h.hexdigest())
PY
}
if [ ! -f "$MODEL" ]; then
  echo "Downloading the free Qwen3 0.6B model (~397 MB)..."
  curl -fL --retry 2 'https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf' -o "$MODEL.part"
  [ "$(sha "$MODEL.part")" = "$MSHA" ] || { rm -f "$MODEL.part"; echo "Model checksum mismatch." >&2; exit 1; }
  mv "$MODEL.part" "$MODEL"
fi
[ "$(sha "$MODEL")" = "$MSHA" ] || { echo "Existing model checksum mismatch." >&2; exit 1; }
if [ ! -x "$DEST/llama-b11669/llama-server" ]; then
  archive="$DEST/llama-$PLATFORM.tar.gz"
  echo "Downloading pinned llama.cpp CPU runtime..."
  curl -fL --retry 2 "https://github.com/ggml-org/llama.cpp/releases/download/b11669/llama-b11669-bin-$PLATFORM.tar.gz" -o "$archive.part"
  [ "$(sha "$archive.part")" = "$ASHA" ] || { rm -f "$archive.part"; echo "Runtime checksum mismatch." >&2; exit 1; }
  mv "$archive.part" "$archive"
  tar -xzf "$archive" -C "$DEST"
fi
[ -x "$DEST/llama-b11669/llama-server" ] || { echo "Runtime executable not found." >&2; exit 1; }
echo "Pinned local model and runtime are available."
