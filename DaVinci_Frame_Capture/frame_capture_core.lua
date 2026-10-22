-- Frame Capture: uses Resolve's native ExportCurrentFrameAsStill API.
local M = {}

function M.normalize_folder(folder)
    if type(folder) ~= 'string' then return nil, '请先选择保存文件夹。' end
    folder = folder:gsub('^%s+', ''):gsub('%s+$', '')
    if folder:sub(1, 1) == '"' and folder:sub(-1) == '"' then folder = folder:sub(2, -2) end
    folder = folder:gsub('\\', '/')
    if folder == '' then return nil, '请先选择保存文件夹。' end
    if folder:find('[%z\r\n"<>|?*]') then return nil, '保存路径包含无效字符。' end
    if not folder:match('^%a:/') and not folder:match('^//[^/]+/[^/]+') then
        return nil, '请选择完整的文件夹路径，例如 D:/Screenshots。'
    end
    if not folder:match('^%a:/$') then folder = folder:gsub('/+$', '') end
    return folder
end

local function join(folder, name)
    return folder .. (folder:sub(-1) == '/' and '' or '/') .. name
end

local function readable(path)
    local file = io.open(path, 'rb')
    if file then file:close(); return true end
    return false
end

function M.new(root, resolve)
    local self = {root = root, resolve = resolve, sequence = 0}
    self.settings_path = join(root, 'save_folder.txt')
    self.folder = join(root, 'Captures')
    self.session = string.format('%06d_%06d', math.floor(os.clock() * 1000000) % 1000000,
                                 math.random(100000, 999999))
    local file = io.open(self.settings_path, 'rb')
    if file then
        local saved = file:read('*a')
        file:close()
        local valid = M.normalize_folder(saved)
        if valid then self.folder = valid end
    end

    function self:set_folder(value)
        local normalized, message = M.normalize_folder(value)
        if not normalized then return nil, message end
        local output, error_message = io.open(self.settings_path, 'wb')
        if not output then return nil, '无法记住保存路径：' .. tostring(error_message) end
        local ok, write_error = output:write(normalized)
        local closed, close_error = output:close()
        if not ok or not closed then
            return nil, '保存路径设置失败：' .. tostring(write_error or close_error)
        end
        self.folder = normalized
        return normalized
    end

    function self:capture()
        local project = self.resolve:GetProjectManager():GetCurrentProject()
        if not project then return nil, '请先打开一个达芬奇工程。' end
        local timeline = project:GetCurrentTimeline()
        if not timeline then return nil, '请先打开要截图的时间线。' end
        local folder, message = M.normalize_folder(self.folder)
        if not folder then return nil, message end
        local timecode = tostring(timeline:GetCurrentTimecode() or 'frame'):gsub('[^%w_-]', '_')
        if timecode == '' then timecode = 'frame' end
        local path
        repeat
            self.sequence = self.sequence + 1
            local filename = string.format('Frame_%s_TC-%s_%s_%04d.png',
                os.date('%Y%m%d_%H%M%S'), timecode, self.session, self.sequence)
            path = join(folder, filename)
        until not readable(path)
        -- Native export handles Unicode destination paths; no screen capture,
        -- render queue, gallery stills, seek operations, or media modifications.
        local ok, exported = pcall(function() return project:ExportCurrentFrameAsStill(path) end)
        if not ok then return nil, '导出失败：' .. tostring(exported) end
        if not exported then
            return nil, '导出失败。请确认文件夹已存在、可写，且当前时间线有可导出的画面。'
        end
        self.last_path = path
        return path, '已保存当前帧。'
    end
    return self
end

return M
