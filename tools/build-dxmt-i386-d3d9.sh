#!/bin/bash
# Rebuild only the emulated i386 D3D9 frontend used by PTDE when
# madeira.cfg contains `d3d9 = emulated`. The native iOS DXMT archive is a
# different frontend and cannot carry instrumentation for this path.
set -euo pipefail

R="$(cd "$(dirname "$0")/.." && pwd)"
TC="$R/toolchains/llvm-mingw-20260421-ucrt-macos-universal/bin"
B="$R/wine/build-i386"
D="$R/research/dxmt"
DB="$D/build-pe-i386-diagnostic"
OUT="$R/build-out"
DEST="$R/app/Madeira/i386-windows/d3d9-emulated.dll"
JOBS="$(sysctl -n hw.ncpu)"
mkdir -p "$OUT"
export PATH="$TC:$PATH"

for tool in i686-w64-mingw32-clang i686-w64-mingw32-clang++ \
            i686-w64-mingw32-ar i686-w64-mingw32-strip \
            i686-w64-mingw32-windres i686-w64-mingw32-dlltool; do
  test -x "$TC/$tool" || { echo "::error::missing $TC/$tool"; exit 1; }
done
test -x "$R/wine/build-native/tools/widl/widl" || {
  echo "::error::native Wine tools are missing"; exit 1;
}

if [ ! -f "$B/Makefile" ]; then
  mkdir -p "$B"
  if ! (cd "$B" && "$R/wine/configure" --enable-archs=i386 \
      --with-wine-tools="$R/wine/build-native" --without-x --without-vulkan \
      --without-freetype --without-gnutls --disable-tests) \
      > "$OUT/wine-i386-dxmt-configure.log" 2>&1; then
    tail -60 "$OUT/wine-i386-dxmt-configure.log"
    echo "::error::Wine i386 configure failed"
    exit 1
  fi
fi

# DXMT's Meson file links the Wine CRT and the ntdll/dbghelp import libraries.
# Build those three archive targets, leaving the shipped i386 Wine farm intact.
DEPS=(
  tools/winebuild/winebuild
  libs/winecrt0/i386-windows/libwinecrt0.a
  dlls/ntdll/i386-windows/libntdll.a
  dlls/dbghelp/i386-windows/libdbghelp.a
)
if ! make -C "$B" -j"$JOBS" "${DEPS[@]}" > "$OUT/wine-i386-dxmt-deps.log" 2>&1; then
  tail -80 "$OUT/wine-i386-dxmt-deps.log"
  echo "::error::Wine i386 DXMT dependencies failed"
  exit 1
fi
for dep in "${DEPS[@]}"; do
  test -s "$B/$dep" || { echo "::error::missing $B/$dep"; exit 1; }
done

X="$OUT/dxmt-i386-cross.ini"
cat > "$X" <<EOF
[binaries]
c = '$TC/i686-w64-mingw32-clang'
cpp = '$TC/i686-w64-mingw32-clang++'
ar = '$TC/i686-w64-mingw32-ar'
strip = '$TC/i686-w64-mingw32-strip'
windres = '$TC/i686-w64-mingw32-windres'
dlltool = '$TC/i686-w64-mingw32-dlltool'

[properties]
needs_exe_wrapper = true

[host_machine]
system = 'windows'
cpu_family = 'x86'
cpu = 'i686'
endian = 'little'
EOF

if ! (cd "$D" && SDKROOT="$(xcrun --sdk macosx --show-sdk-path)" \
    meson setup "$DB" --cross-file "$X" --native-file build-osx.txt \
      --buildtype release -Dwine_build_path="$B" -Dwine_builtin_dll=true) \
    > "$OUT/dxmt-i386-setup.log" 2>&1; then
  tail -80 "$OUT/dxmt-i386-setup.log"
  echo "::error::DXMT i386 setup failed"
  exit 1
fi
if ! SDKROOT="$(xcrun --sdk macosx --show-sdk-path)" \
    meson compile -C "$DB" src/d3d9/d3d9.dll \
    > "$OUT/dxmt-i386-build.log" 2>&1; then
  tail -100 "$OUT/dxmt-i386-build.log"
  echo "::error::DXMT i386 D3D9 build failed"
  exit 1
fi

SOURCE="$DB/src/d3d9/d3d9.dll"
test -s "$SOURCE"
TMP="$DEST.diagnostic.tmp"
"$TC/i686-w64-mingw32-strip" -o "$TMP" "$SOURCE"
python3 - "$TMP" <<'PY'
import mmap, struct, sys
with open(sys.argv[1], 'rb') as binary:
    with mmap.mmap(binary.fileno(), 0, access=mmap.ACCESS_READ) as data:
        if data[:2] != b'MZ':
            raise SystemExit('rebuilt D3D9 module is not PE')
        pe = struct.unpack_from('<I', data, 0x3c)[0]
        if data[pe:pe + 4] != b'PE\0\0' or struct.unpack_from('<H', data, pe + 4)[0] != 0x14c:
            raise SystemExit('rebuilt D3D9 module is not i386 PE')
        if b'native GetRenderTargetData timing active' not in data:
            raise SystemExit('D3D9 timing marker missing from rebuilt emulated DLL')
PY
mv "$TMP" "$DEST"
echo "::notice::rebuilt i386 d3d9-emulated.dll with readback timing: $(wc -c < "$DEST") bytes"
