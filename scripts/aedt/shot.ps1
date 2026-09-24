# Full-screen capture on the remote PC, saved to Desktop\aedtgui.png.
# Chrome Remote Desktop does not show AEDT's graphics area (3D view and 2D reports); this
# checks whether a capture taken on the Windows side does. Run from a PowerShell window as
#   powershell -ep bypass -file desktop\shot.ps1
# (lower case, no colon: the remote session drops Shift). It waits 8 s so AEDT can be
# brought to the front after starting it.
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type 'using System; using System.Runtime.InteropServices; public class Dpi { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }'
[Dpi]::SetProcessDPIAware() | Out-Null
Start-Sleep -Seconds 8
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
$out = Join-Path $env:USERPROFILE 'Desktop\aedtgui.png'
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
"saved $out  $($b.Width) x $($b.Height)"
