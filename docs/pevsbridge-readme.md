# PE VS Bridge

`PEVsBridge.vsix` is a VS 2017 in-process package for authorized reading and
writing of PE-protected source. It replaces the unsupported `.AddIn` approach
and never exposes Visual Studio's DTE automation object to external tools.

## Install and verify

1. Install `bin/Release/PEVsBridge.vsix` with VSIXInstaller.
2. Start the same Visual Studio instance in which it was installed and open the
   PE solution/project. The package auto-loads when a solution exists.
3. Run `python pe_vs_bridge_client.py status`.
5. Read an encrypted source through VS:

   ```powershell
   python pe_vs_bridge_client.py read PEHelloMCP/HelloMCPService.cpp
   ```

## Safe update transaction

1. `read` returns `sha256` and plaintext from VS's text buffer.
2. Write the desired full replacement to a normal UTF-8 staging file.
3. Call `replace --expected-sha256 <hash> --text-file staged.cpp`.
4. Call `save` only after inspecting the replacement response.

The bridge uses the fixed local named pipe `\\.\pipe\PE.VSBridge`. Its Windows
ACL permits only the Windows user that started Visual Studio; no discovery/token
file is written, so the PE file-encryption filter cannot corrupt the protocol.
The bridge rejects paths outside the active solution and refuses a replacement
when the source hash changed since the read. All protected-file reads and writes
occur inside the Visual Studio process through `IVsTextLines`.

## Experimental instance note

VSIX packages installed for the VS SDK experimental hive (`/RootSuffix Exp`) are
not visible to the normal VS instance. Install the VSIX in the intended instance,
then start that same instance with the PE project open.
