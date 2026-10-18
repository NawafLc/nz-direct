# boiii changes

NZ Direct runs a modified [boiii-free](https://github.com/Ezz-lol/boiii-free)
(GPL-3.0). The changes are here as patches so the `boiii.exe` in the releases
can be rebuilt from source.

Upstream commit: `5aa7fac39c51438d9c1e312b99534b7fef3bff44`.
The `deps/minhook` submodule is at `8af6b4acae5a9388fd742b56fa79ece89d96f823`.

| File | What it changes |
| --- | --- |
| `boiii-free.patch` | New `direct_launch` component: `+set direct_map` boots straight into a match (`direct_mod`, `direct_exit`, `direct_log`); also registers `nzd_bgb` for the launcher's Gobblegum pack. Other changes: `wmi_startup.cpp` skips the slow BitLocker WMI query at startup. `com.cpp` skips the multiplayer-only `core_specialists` zones when direct-launching. `patches.cpp` relaunches the map after a "Clientfield Mismatch" error. `client_command.cpp` leaves ClientCommand unhooked in direct-launch sessions, because the hook can stall the local server |
| `minhook.patch` | Faster hook installation (`src/hook.c` in the minhook submodule) |
| `premake_shim.lua` | Build helper for premake beta versions that lack newer API names |

## Build

```bat
git clone --recursive https://github.com/Ezz-lol/boiii-free
cd boiii-free
git checkout 5aa7fac39c51438d9c1e312b99534b7fef3bff44
git submodule update --init --recursive
git apply ..\nz-direct\boiii\boiii-free.patch
git -C deps/minhook apply ..\..\..\nz-direct\boiii\minhook.patch
copy ..\nz-direct\boiii\premake_shim.lua .
```

Then build as described in boiii-free (premake5 `vs2022`, Release x64). If
your premake version fails, run it with `--file=premake_shim.lua`.

The direct-launch features need the BlackOps3.exe that boiii-free supports
(PE checksum `0x6531394`). The setup script downloads that exe and checks it.
