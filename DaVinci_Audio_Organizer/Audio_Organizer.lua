-- Audio Organizer v1.0: Resolve menu entry. No external scripting permission needed.
-- Keep the installed package in this folder, or update ROOT if you relocate it.
local ROOT = "C:/Users/1/Documents/Codex/Tools/DaVinci_Audio_Organizer"
local PYTHON = "C:/Users/1/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/pythonw.exe"

local function quote(path)
    assert(not string.find(path, '[%%"\r\n]'), "Unsupported character in tool path")
    return '"' .. path .. '"'
end

local function invoke(arguments)
    local command = quote(PYTHON) .. ' ' .. quote(ROOT .. '/audio_organizer.py')
    for _, arg in ipairs(arguments) do command = command .. ' ' .. quote(arg) end
    -- Pythonw runs synchronously and writes diagnostics into the run folder.
    -- Outer quotes are required by Windows cmd when the executable is quoted.
    os.execute('"' .. command .. '"')
end

local function exists(path)
    local f = io.open(path, 'rb')
    if f then f:close(); return true end
    return false
end

local function method(object, name)
    if type(object) ~= 'table' and type(object) ~= 'userdata' then return nil end
    local ok, value = pcall(function() return object[name] end)
    if ok and type(value) == 'function' then return value end
    return nil
end

local function clip_objects(timeline, index)
    local result, seen = {}, {}
    for _, item in pairs(timeline:GetItemListInTrack('audio', index) or {}) do
        if method(item, 'SetClipColor') and method(item, 'GetStart') then
            local key = item
            if method(item, 'GetUniqueId') then
                local ok, id = pcall(function() return item:GetUniqueId() end)
                if ok and id then key = id end
            end
            if not seen[key] then
                seen[key] = true
                result[#result + 1] = item
            end
        end
    end
    return result
end

local function load_result(path)
    local loader, error_message = loadfile(path)
    assert(loader, 'Worker did not produce a readable result: ' .. tostring(error_message))
    local result = loader()
    assert(type(result) == 'table', 'Invalid worker result')
    assert(result.status ~= 'error', 'Audio Organizer: ' .. tostring(result.message))
    return result
end

local function worker(input, run_dir, suffix)
    local result_path = run_dir .. '/result_' .. suffix .. '.lua'
    invoke({'--input', input, '--output', run_dir .. '/organized.drt',
            '--rules', ROOT .. '/rules.json', '--report', run_dir .. '/report_' .. suffix,
            '--result', result_path})
    return load_result(result_path)
end

local resolve = Resolve()
assert(resolve, 'Run Audio Organizer inside DaVinci Resolve')
local project = resolve:GetProjectManager():GetCurrentProject()
local source = project and project:GetCurrentTimeline()
assert(source, 'Open a project and a timeline first')
local run_dir
local imported

local function run()
    assert(exists(PYTHON), 'Configured Python runtime is missing: ' .. PYTHON)
    assert(exists(ROOT .. '/audio_organizer.py'), 'Audio Organizer package is missing')
    assert(exists(ROOT .. '/rules.json'), 'Classification rules are missing')
    local count = source:GetTrackCount('audio')
    assert(count > 0, 'Current timeline has no audio tracks')
    local format
    for i = 1, count do
        local current_format = source:GetTrackSubType('audio', i)
        assert(current_format == 'mono' or current_format == 'stereo',
               'Version 1 supports mono-only or stereo-only timelines')
        assert(not format or format == current_format,
               'Version 1 cannot organize mixed mono/stereo tracks automatically')
        format = current_format
        assert(source:GetIsTrackEnabled('audio', i), 'Unmute audio track A' .. i .. ' before running')
        assert(not source:GetIsTrackLocked('audio', i), 'Unlock audio track A' .. i .. ' before running')
    end
    local stamp = os.date('%Y%m%d_%H%M%S') .. '_' .. tostring(math.random(100000, 999999))
    run_dir = ROOT .. '/runs/' .. stamp
    invoke({'--init-run', run_dir})
    assert(exists(run_dir .. '/initialized.txt'), 'Could not initialize worker; check the Python runtime')
    local backup = run_dir .. '/original.drt'
    print('Audio Organizer: exporting a native DRT backup...')
    assert(source:Export(backup, resolve.EXPORT_DRT, resolve.EXPORT_NONE), 'DRT export failed')
    local result = worker(backup, run_dir, 'initial')
    if result.status == 'needs_tracks' then
        print('Audio Organizer: preparing ' .. result.required_tracks .. ' tracks in a duplicate...')
        local prep = source:DuplicateTimeline(source:GetName() .. '_Audio_Prepare_' .. stamp)
        assert(prep, 'Could not create a preparation copy')
        assert(project:SetCurrentTimeline(prep), 'Could not select the preparation copy')
        for i = count + 1, result.required_tracks do
            assert(prep:AddTrack('audio', format), 'Could not add native audio track A' .. i)
        end
        local padded = run_dir .. '/prepared.drt'
        assert(prep:Export(padded, resolve.EXPORT_DRT, resolve.EXPORT_NONE), 'Preparation export failed')
        result = worker(padded, run_dir, 'final')
        -- Keep this preparation copy so no timeline needs to be deleted automatically.
    end
    assert(result.status == 'ready', 'Worker could not produce a grouped timeline')
    print('Audio Organizer: importing grouped native DRT...')
    imported = project:GetMediaPool():ImportTimelineFromFile(result.output)
    assert(imported, 'DRT import failed; the original timeline is preserved')
    assert(imported:SetName(source:GetName() .. '_Audio_Organized_' .. stamp), 'Could not name the new timeline')
    assert(imported:GetTrackCount('audio') == #result.tracks, 'Imported audio track count mismatch')
    assert(imported:GetTrackCount('video') == source:GetTrackCount('video'), 'Video track count mismatch')
    assert(imported:GetTrackCount('subtitle') == source:GetTrackCount('subtitle'), 'Subtitle track count mismatch')
    assert(imported:GetStartFrame() == source:GetStartFrame() and
           imported:GetEndFrame() == source:GetEndFrame(), 'Imported timeline extent mismatch')
    for i, track in ipairs(result.tracks) do
        assert(imported:GetTrackName('audio', i) == track.name, 'Imported track name mismatch on A' .. i)
    end
    local colored, failed = 0, 0
    for i, track in ipairs(result.tracks) do
        local items = clip_objects(imported, i)
        if #items ~= track.clip_count then
            print('CHECK A' .. i .. ': native API reports ' .. #items ..
                  ' clips; exported DRT contains ' .. track.clip_count)
        end
        if track.color ~= '' then
            for _, item in ipairs(items) do
                local ok, applied = pcall(function()
                    return item:SetClipColor(track.color) and item:GetClipColor() == track.color
                end)
                if ok and applied then colored = colored + 1 else failed = failed + 1 end
            end
        end
        print('A' .. i .. ': ' .. track.name .. ' / ' .. #items .. ' clips / ' .. track.color)
    end
    assert(project:SetCurrentTimeline(imported), 'Could not select grouped timeline')
    resolve:OpenPage('edit')
    print('Audio Organizer DONE: ' .. colored .. ' colored; ' .. failed .. ' color errors; ' ..
          result.review_clips .. ' clips need classification review.')
    print('Backup and classification report: ' .. run_dir)
    print('Original timeline preserved. Check audio playback and track-level mixing before delivery.')
end

local ok, error_message = xpcall(run, debug.traceback)
if not ok then
    pcall(function() project:SetCurrentTimeline(source) end)
    print('Audio Organizer STOPPED: ' .. tostring(error_message))
    if run_dir then print('Diagnostic folder: ' .. run_dir) end
end
