#!/bin/bash
# Rebuild the 32-bit WoW64 CPU module. The tracked xtajit.dll predates the
# 125hz fix for native TLS access while Wine is entering a WoW64 process.
set -euo pipefail

ROOT="$(pwd)"
SOURCE="$ROOT/build/fex-wow64-source"
BUILD="$ROOT/build/fex-wow64-build"
DEST="$ROOT/app/Madeira/aarch64-windows/xtajit.dll"
MINGW="$ROOT/toolchains/llvm-mingw-20260421-ucrt-macos-universal/bin"
FEX_REV=7b528d8a57cb12b794c589dd7e42fff813fc9abd
export PATH="$MINGW:$PATH"

test -x "$MINGW/aarch64-w64-mingw32-clang++"
test -s "$DEST"
mkdir -p "$ROOT/build"
# Reuse the already checked out FEX Git object store, but keep this revision's
# source isolated from the iOS static-library patches and ARM64EC module build.
git -C FEX fetch --depth 1 https://github.com/125hz/FEX.git "$FEX_REV"
git -C FEX worktree add --detach "$SOURCE" "$FEX_REV"
test "$(git -C "$SOURCE" rev-parse HEAD)" = "$FEX_REV"
git -C "$SOURCE" submodule update --init --recursive --depth 1

# Guard the two fixed call sites before compiling. A branch revision alone is
# insufficient: a stale committed DLL had the same nominal FEX snapshot.
grep -q 'std::atomic<uint64_t> IRCapRIP' "$SOURCE/FEXCore/Source/Interface/IR/PassManager.cpp"
grep -q 'mrs %0, TPIDRRO_EL0' "$SOURCE/FEXCore/Source/Utils/AllocWatch.cpp"

cmake -S "$SOURCE" -B "$BUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE="$SOURCE/Data/CMake/toolchain_mingw.cmake" \
  -DMINGW_TRIPLE=aarch64-w64-mingw32 -DTUNE_CPU=cortex-a78 \
  -DFEX_IOS_HOST_BUILD=ON \
  -DCMAKE_C_FLAGS=-DFEX_IOS_HOST=1 -DCMAKE_CXX_FLAGS=-DFEX_IOS_HOST=1 \
  -DCMAKE_ASM_FLAGS=-DFEX_IOS_HOST=1 \
  -DENABLE_LTO=OFF -DENABLE_FEX_ALLOCATOR=ON -DENABLE_JEMALLOC_GLIBC_ALLOC=ON \
  -DBUILD_FEXCONFIG=OFF -DENABLE_CCACHE=OFF -DBUILD_TESTING=OFF -DBUILD_THUNKS=OFF \
  -DENABLE_ASSERTIONS=OFF > "$ROOT/xtajit-wow64-configure.log" 2>&1 || {
    tail -60 "$ROOT/xtajit-wow64-configure.log"
    exit 1
  }
cmake --build "$BUILD" --target wow64fex -j"$(sysctl -n hw.ncpu)" \
  > "$ROOT/xtajit-wow64-build.log" 2>&1 || {
    grep -m 25 -B 2 -A 3 'error:' "$ROOT/xtajit-wow64-build.log" || tail -60 "$ROOT/xtajit-wow64-build.log"
    exit 1
  }

DLL="$BUILD/Bin/libwow64fex.dll"
test -s "$DLL"
python3 - "$DEST" "$DLL" <<'PY'
import hashlib, struct, sys

def inspect(path):
    data = open(path, 'rb').read()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    assert data[pe:pe+4] == b'PE\0\0', path
    assert struct.unpack_from('<H', data, pe+4)[0] == 0xaa64, path
    count = struct.unpack_from('<H', data, pe+6)[0]
    off = pe+24+struct.unpack_from('<H', data, pe+20)[0]
    sections = {}
    for i in range(count):
        p = off+40*i
        name = data[p:p+8].rstrip(b'\0').decode()
        sections[name] = struct.unpack_from('<I', data, p+8)[0]
    return hashlib.sha256(data).hexdigest(), sections

old_hash, old_sections = inspect(sys.argv[1])
new_hash, new_sections = inspect(sys.argv[2])
print('tracked xtajit.dll:', old_hash, old_sections)
print('rebuilt xtajit.dll:', new_hash, new_sections)
assert old_hash != new_hash, 'the old 32-bit DLL would still be shipped'
assert '.text' in new_sections and '.pdata' in new_sections
assert new_sections.get('.tls', 0) == 0, 'native TLS remains in the rebuilt WoW64 module'
PY

# Wine expects this precise name in aarch64-windows; the Xcode folder resource
# copies that directory into the IPA without a per-file project reference.
cp "$DLL" "$DEST"
echo "::notice::replaced aarch64-windows/xtajit.dll with TLS-free WoW64 build from $FEX_REV"
