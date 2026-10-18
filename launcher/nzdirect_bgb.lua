-- NZ Direct Gobblegum pack (installed by the NZ Direct launcher into
-- <GameRoot>/boiii/ui_scripts/nzdirect_bgb/__init__.lua).
--
-- The launcher starts the game with `+set nzd_bgb gum1,gum2,...` (up to 5
-- zm_bgb_* names). This puts them into the equipped Gobblegum pack the same
-- way the game's own pack editor does (Engine.SetBubbleGumBuff), so the pack
-- screen, the GobbleGum machines and mods that read the pack all use it, and
-- in someone else's match the host gets this player's own pack.
-- Inert without the dvar. Results: `nzd_bgb_status` dvar and [NZD] log lines.

local function log(text)
  print("[NZD] bgb: " .. text)
  pcall(Engine.SetDvar, "nzd_bgb_status", text)
  -- With -unsafe-lua (or a mod that needs it) the result also goes to a file.
  if io and io.open then
    local f = io.open("nzdirect_bgb.log", "a")
    if f then
      f:write(text, "\n")
      f:close()
    end
  end
end

local okDvar, wanted = pcall(Engine.DvarString, nil, "nzd_bgb")
if not okDvar or type(wanted) ~= "string" or wanted == "" then
  log("inactive (nzd_bgb=" .. tostring(wanted) .. ")")
  return
end

local gums = {}
for gum in string.gmatch(wanted, "[%w_]+") do
  if #gums < 5 then
    gums[#gums + 1] = gum
  end
end

local function call(f, ...)
  if type(f) ~= "function" then
    return false, "missing"
  end
  return pcall(f, ...)
end

local zombies = Enum and Enum.eModes and Enum.eModes.MODE_ZOMBIES

-- Item indices of the gums (the game's own lookup, dumped once). While a mod
-- loads, the lookup isn't available yet, so these are the fallback.
local KNOWN = {
  zm_bgb_aftertaste = 216, zm_bgb_alchemical_antithesis = 201, zm_bgb_always_done_swiftly = 202,
  zm_bgb_anywhere_but_here = 203, zm_bgb_armamental_accomplishment = 204, zm_bgb_arms_grace = 205,
  zm_bgb_arsenal_accelerator = 206, zm_bgb_board_games = 254, zm_bgb_board_to_death = 255,
  zm_bgb_bullet_boost = 247, zm_bgb_burned_out = 217, zm_bgb_cache_back = 218, zm_bgb_coagulant = 207,
  zm_bgb_crate_power = 242, zm_bgb_crawl_space = 234, zm_bgb_danger_closest = 208,
  zm_bgb_dead_of_nuclear_winter = 219, zm_bgb_disorderly_combat = 243, zm_bgb_ephemeral_enhancement = 220,
  zm_bgb_extra_credit = 197, zm_bgb_eye_candy = 196, zm_bgb_fatal_contraption = 235,
  zm_bgb_fear_in_headlights = 238, zm_bgb_firing_on_all_cylinders = 209, zm_bgb_flavor_hexed = 195,
  zm_bgb_head_drama = 236, zm_bgb_idle_eyes = 194, zm_bgb_immolation_liquidation = 222,
  zm_bgb_impatient = 210, zm_bgb_in_plain_sight = 211, zm_bgb_kill_joy = 223, zm_bgb_killing_time = 224,
  zm_bgb_licensed_contractor = 225, zm_bgb_lucky_crit = 212, zm_bgb_mind_blown = 248,
  zm_bgb_near_death_experience = 249, zm_bgb_newtonian_negation = 250, zm_bgb_now_you_see_me = 213,
  zm_bgb_on_the_house = 226, zm_bgb_perkaholic = 227, zm_bgb_phoenix_up = 228, zm_bgb_pop_shocks = 229,
  zm_bgb_power_vacuum = 193, zm_bgb_profit_sharing = 251, zm_bgb_projectile_vomiting = 244,
  zm_bgb_reign_drops = 192, zm_bgb_respin_cycle = 230, zm_bgb_round_robbin = 252,
  zm_bgb_secret_shopper = 239, zm_bgb_self_medication = 253, zm_bgb_shopping_free = 245,
  zm_bgb_slaughter_slide = 246, zm_bgb_soda_fountain = 191, zm_bgb_stock_option = 214,
  zm_bgb_sword_flay = 215, zm_bgb_temporal_gift = 240, zm_bgb_tone_death = 190, zm_bgb_unbearable = 241,
  zm_bgb_undead_man_walking = 237, zm_bgb_unquenchable = 231, zm_bgb_wall_power = 232,
  zm_bgb_whos_keeping_score = 233,
}

local function itemIndex(ref)
  local ok, index = call(Engine.GetItemIndexFromReference, ref, zombies)
  if ok and type(index) == "number" and index > 0 then
    return index
  end
  return KNOWN[ref]
end

local okController, controller = call(Engine.GetPrimaryController)
if not okController or type(controller) ~= "number" then
  controller = 0
end
local okPack, pack = call(Engine.GetEquippedBubbleGumPack, controller)
if not okPack or type(pack) ~= "number" then
  log("no equipped pack (" .. tostring(pack) .. ")")
  return
end

local before = {}
for slot = 0, 4 do
  local _, current = call(Engine.GetBubbleGumBuff, controller, pack, slot)
  before[#before + 1] = tostring(current)
end

local results = {}
for slot, gum in ipairs(gums) do
  local index = itemIndex(gum)
  if index then
    local ok, err = call(Engine.SetBubbleGumBuff, controller, pack, slot - 1, index)
    local _, now = call(Engine.GetBubbleGumBuff, controller, pack, slot - 1)
    results[#results + 1] = gum .. "=" .. index .. (ok and "" or (" ERR " .. tostring(err)))
      .. (now == index and "" or (" readback " .. tostring(now)))
  else
    results[#results + 1] = gum .. "=unknown"
  end
end

log("pack " .. pack .. " before [" .. table.concat(before, ",") .. "] set " .. table.concat(results, " "))
