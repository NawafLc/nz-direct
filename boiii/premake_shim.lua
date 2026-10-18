-- Shim for premake beta builds lacking newer API names used by boiii-free.
local function boolapi(name, flag)
  if _G[name] == nil then
    _G[name] = function(v)
      if v == "Off" and flag then flags({ flag }) end
      if v == "On" and name == "multiprocessorcompile" then flags({ "MultiProcessorCompile" }) end
    end
  end
end
boolapi("incrementallink", "NoIncrementalLink")
boolapi("minimalrebuild", "NoMinimalRebuild")
boolapi("multiprocessorcompile", nil)
boolapi("enable64bitchecks", nil)
boolapi("runtimechecks", "NoRuntimeChecks")
boolapi("buffersecuritycheck", "NoBufferSecurityCheck")
boolapi("nodefaultlib", nil)
dofile(_MAIN_SCRIPT_DIR .. "/premake5.lua")
