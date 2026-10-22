-- Direct menu action: export immediately to the folder selected in the panel.
local source = debug.getinfo(1, 'S').source
assert(source:sub(1, 1) == '@', '请从达芬奇脚本菜单运行。')
local root = source:sub(2):gsub('\\', '/'):match('^(.*)/[^/]+$')
assert(root, '无法定位截图工具文件夹。')
local core = assert(loadfile(root .. '/frame_capture_core.lua'))()
local controller = core.new(root, assert(Resolve(), '请在达芬奇中运行。'))
local ok, path, message = pcall(function() return controller:capture() end)
if ok and path then
    print('[Frame Capture] 已保存：' .. path)
else
    local status = ok and message or tostring(path)
    print('[Frame Capture] ' .. tostring(status))
    assert(loadfile(root .. '/Frame_Capture_Panel.lua'))(status)
end
