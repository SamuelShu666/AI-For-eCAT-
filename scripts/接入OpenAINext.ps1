$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskStatusPath = Join-Path $taskRoot '.local\connection-status.json'
$taskRuntime = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $taskRuntime)) { throw 'Bundled Python runtime is missing.' }
New-Item -ItemType Directory -Path (Split-Path -Parent $taskStatusPath) -Force | Out-Null
@{status='awaiting_local_key'} | ConvertTo-Json | Set-Content -LiteralPath $taskStatusPath -Encoding UTF8

$taskForm = New-Object System.Windows.Forms.Form
$taskForm.Text = 'OpenAINext 本机接入'
$taskForm.Size = New-Object System.Drawing.Size(590,265)
$taskForm.StartPosition = 'CenterScreen'
$taskForm.FormBorderStyle = 'FixedDialog'
$taskForm.MaximizeBox = $false
$taskForm.MinimizeBox = $false
$taskForm.TopMost = $true
$taskLabel = New-Object System.Windows.Forms.Label
$taskLabel.Location = New-Object System.Drawing.Point(20,18)
$taskLabel.Size = New-Object System.Drawing.Size(540,85)
$taskLabel.Text = "在此粘贴 OpenAINext API 密钥，输入内容不会显示。`r`n将进行一次小额 OK 测试，成功后配置比赛项目与 Codex。`r`n仅连接 api.openai-next.com；保留现有 auth.json 并备份配置。`r`n密钥保存到当前 Windows 用户的 OPENAINEXT_API_KEY 环境变量。"
$taskBox = New-Object System.Windows.Forms.TextBox
$taskBox.Location = New-Object System.Drawing.Point(20,110)
$taskBox.Size = New-Object System.Drawing.Size(535,28)
$taskBox.UseSystemPasswordChar = $true
$taskOK = New-Object System.Windows.Forms.Button
$taskOK.Text = '测试并接入'
$taskOK.Location = New-Object System.Drawing.Point(320,165)
$taskOK.Size = New-Object System.Drawing.Size(115,32)
$taskOK.DialogResult = [System.Windows.Forms.DialogResult]::OK
$taskCancel = New-Object System.Windows.Forms.Button
$taskCancel.Text = '取消'
$taskCancel.Location = New-Object System.Drawing.Point(445,165)
$taskCancel.Size = New-Object System.Drawing.Size(110,32)
$taskCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$taskForm.Controls.AddRange(@($taskLabel,$taskBox,$taskOK,$taskCancel))
$taskForm.AcceptButton = $taskOK
$taskForm.CancelButton = $taskCancel
$taskResult = $taskForm.ShowDialog()
if ($taskResult -ne [System.Windows.Forms.DialogResult]::OK) {
    @{status='cancelled';configuration_changed=$false} | ConvertTo-Json | Set-Content -LiteralPath $taskStatusPath -Encoding UTF8
    $taskForm.Dispose()
    exit 0
}
$env:OPENAINEXT_SETUP_KEY = $taskBox.Text.Trim()
$taskBox.Clear()
$taskForm.Dispose()
try {
    & $taskRuntime (Join-Path $PSScriptRoot 'connect_openainext.py') --status $taskStatusPath | Out-Null
    $taskExitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:\OPENAINEXT_SETUP_KEY -ErrorAction SilentlyContinue
}
if ($taskExitCode -eq 0) {
    [System.Windows.Forms.MessageBox]::Show('连接测试通过，项目调用模块已接好。请完全退出并重新打开 Codex，然后发送一句测试消息。当前聊天尚未自动切换。','OpenAINext 接入完成') | Out-Null
} else {
    [System.Windows.Forms.MessageBox]::Show('接入未完成，尚未切换桌面服务。请回到聊天，我会检查不含密钥的状态记录。','OpenAINext 接入结果') | Out-Null
}

