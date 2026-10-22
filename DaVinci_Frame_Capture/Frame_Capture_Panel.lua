-- Native Resolve floating capture panel. Open from Workspace > Scripts.
local initial_status = ...
local source = debug.getinfo(1, 'S').source
assert(source:sub(1, 1) == '@', '请从脚本菜单或 dofile 打开截图面板。')
local root = source:sub(2):gsub('\\', '/'):match('^(.*)/[^/]+$')
assert(root, '无法定位截图工具文件夹。')
local core = assert(loadfile(root .. '/frame_capture_core.lua'))()
local resolve = Resolve()
assert(resolve, '请在达芬奇中运行截图工具。')
local fusion = resolve:Fusion()
assert(fusion and bmd, '当前版本不支持达芬奇脚本界面。')
local ui = fusion.UIManager
if type(ui) == 'function' then ui = fusion:UIManager() end
assert(ui, 'UIManager 不可用；请使用 DaVinci Resolve Studio。')
local existing = ui:FindWindow('NativeFrameCapturePanel')
if existing then existing:Show(); existing:Raise(); return end
local controller = core.new(root, resolve)
local dispatcher = bmd.UIDispatcher(ui)
local window = dispatcher:AddWindow({
    ID = 'NativeFrameCapturePanel', WindowTitle = '当前帧截图',
    Geometry = {260, 160, 540, 220},
    WindowFlags = {Window = true, WindowStaysOnTopHint = true},
    ui:VGroup{
        Spacing = 8,
        ui:Label{Text = '保存当前时间线播放头位置的画面', Weight = 0},
        ui:HGroup{
            Weight = 0,
            ui:LineEdit{ID = 'SaveFolder', Text = controller.folder,
                ToolTip = '可以选择现有文件夹，也可以粘贴完整路径。'},
            ui:Button{ID = 'ChooseFolder', Text = '选择文件夹', Weight = 0},
        },
        ui:Button{ID = 'Capture', Text = '截图并保存（PNG）', MinimumSize = {0, 54},
            ToolTip = '调用达芬奇原生“将当前帧保存为静帧”，自动命名保存。'},
        ui:Label{ID = 'Status', Text = type(initial_status) == 'string' and initial_status
            or '选好文件夹后，点击按钮即可保存。', WordWrap = true, Weight = 0},
        ui:LineEdit{ID = 'LastFile', Text = '', ReadOnly = true,
            PlaceholderText = '截图完成后显示文件路径，可选中复制。', Weight = 0},
    }
})
local items = window:GetItems()

local function guarded(action)
    local ok, message = xpcall(action, debug.traceback)
    if not ok then
        items.Status.Text = '操作失败：' .. tostring(message)
        print('[Frame Capture] ' .. tostring(message))
    end
end

function window.On.ChooseFolder.Clicked(event)
    guarded(function()
        local ok, directory = pcall(function() return fusion:RequestDir(items.SaveFolder.Text) end)
        if not ok then
            items.Status.Text = '文件夹选择器不可用，请直接在上方粘贴已有文件夹的完整路径。'
            return
        end
        if not directory or directory == '' then return end
        local saved, message = controller:set_folder(directory)
        if not saved then items.Status.Text = message; return end
        items.SaveFolder.Text = saved
        items.Status.Text = '保存文件夹已记住。'
    end)
end

function window.On.SaveFolder.EditingFinished(event)
    guarded(function()
        local saved, message = controller:set_folder(items.SaveFolder.Text)
        if saved then
            items.SaveFolder.Text = saved
            items.Status.Text = '保存文件夹已记住。'
        else items.Status.Text = message end
    end)
end

function window.On.Capture.Clicked(event)
    guarded(function()
        local saved, message = controller:set_folder(items.SaveFolder.Text)
        if not saved then items.Status.Text = message; return end
        items.Capture.Enabled = false
        items.Status.Text = '正在保存当前帧…'
        local ok, path, status = pcall(function() return controller:capture() end)
        items.Capture.Enabled = true
        if not ok then items.Status.Text = '导出失败：' .. tostring(path); return end
        if not path then items.Status.Text = status; return end
        items.LastFile.Text = path
        items.Status.Text = '已保存：' .. path:match('[^/]+$')
        print('[Frame Capture] ' .. path)
    end)
end

function window.On.NativeFrameCapturePanel.Close(event)
    dispatcher:ExitLoop()
end

window:Show()
dispatcher:RunLoop()
window:Hide()
