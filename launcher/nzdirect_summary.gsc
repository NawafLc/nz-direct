// NZ Direct match summary (installed by the NZ Direct launcher).
//
// Writes boiii\scriptdata\nzdirect\match.json at the end of every round and
// when the game ends, so the launcher can show the match in its history even
// if the game is closed mid-match. Uses no clientfields or shared scripts, so
// it does not interfere with mods.

function autoexec nzdirect_summary_init()
{
    level thread nzdirect_rounds();
    level thread nzdirect_game_over();
}

function nzdirect_rounds()
{
    level endon("end_game");
    for (;;)
    {
        level waittill("end_of_round");
        nzdirect_write(false);
    }
}

function nzdirect_game_over()
{
    level waittill("end_game");
    nzdirect_write(true);
}

function nzdirect_stat(player, name)
{
    if (isdefined(player.pers) && isdefined(player.pers[name]))
    {
        return player.pers[name];
    }
    return 0;
}

function nzdirect_clean(text)
{
    out = "";
    for (i = 0; i < text.size; i++)
    {
        c = text[i];
        if (c != "\"" && c != "\\")
        {
            out = out + c;
        }
    }
    return out;
}

function nzdirect_write(final)
{
    round = 0;
    if (isdefined(level.round_number))
    {
        round = level.round_number;
    }

    json = "{\"map\":\"" + GetDvarString("mapname") + "\"";
    json = json + ",\"round\":" + round;
    json = json + ",\"time_ms\":" + GetTime();
    if (final)
    {
        json = json + ",\"final\":true";
    }
    else
    {
        json = json + ",\"final\":false";
    }
    json = json + ",\"players\":[";

    players = GetPlayers();
    for (i = 0; i < players.size; i++)
    {
        p = players[i];
        if (i > 0)
        {
            json = json + ",";
        }
        points = 0;
        if (isdefined(p.score))
        {
            points = p.score;
        }
        json = json + "{\"name\":\"" + nzdirect_clean(p.name) + "\"";
        json = json + ",\"points\":" + points;
        json = json + ",\"score\":" + nzdirect_stat(p, "score");
        json = json + ",\"kills\":" + nzdirect_stat(p, "kills");
        json = json + ",\"headshots\":" + nzdirect_stat(p, "headshots");
        json = json + ",\"downs\":" + nzdirect_stat(p, "downs");
        json = json + ",\"revives\":" + nzdirect_stat(p, "revives");
        json = json + "}";
    }
    json = json + "]}";

    writefile("nzdirect/match.json", json);
}
