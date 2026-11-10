# Project Nightmare - Persistent PowerPoint COM Worker
$ErrorActionPreference = 'Continue'
$stdin = [Console]::In
$stdout = [Console]::Out

function Safe-GetPPT {
    try {
        return [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application')
    } catch {
        return $null
    }
}

function Ensure-SlideShow($ppt) {
    try {
        if ($ppt.SlideShowWindows.Count -eq 0) {
            if ($null -ne $ppt.ActivePresentation -and $ppt.Presentations.Count -gt 0) {
                $null = $ppt.ActivePresentation.SlideShowSettings.Run()
                Start-Sleep -Milliseconds 60
            }
        }
    } catch {
        # Ignore if busy or cannot start slideshow
    }
}

function Handle-Open($path, $slideNum) {
    try {
        $ppt = Safe-GetPPT
        if ($null -eq $ppt) {
            $ppt = New-Object -ComObject PowerPoint.Application
        }
        $ppt.Visible = 1
        $pres = $ppt.Presentations.Open($path)
        $ss = $pres.SlideShowSettings.Run()
        $sIdx = [int]$slideNum
        if ($ss -and $ss.View) {
            $ss.View.GotoSlide($sIdx)
        } elseif ($ppt.ActiveWindow -and $ppt.ActiveWindow.View) {
            $ppt.ActiveWindow.View.GotoSlide($sIdx)
        }
        return 'OK:Presentation opened'
    } catch {
        return ('ERROR:Could not open presentation: ' + $_.Exception.Message)
    }
}

function Handle-Start {
    $ppt = Safe-GetPPT
    if ($null -eq $ppt) {
        return 'ERROR:PowerPoint is not currently running.'
    }
    try {
        if ($null -eq $ppt.Presentations -or $ppt.Presentations.Count -eq 0) {
            return 'ERROR:No presentation is open in PowerPoint.'
        }
    } catch {
        return 'ERROR:PowerPoint is busy or blocked by a modal dialog.'
    }

    try {
        $null = $ppt.ActivePresentation.SlideShowSettings.Run()
        return 'OK:Slide show started.'
    } catch {
        return ('ERROR:Could not start presentation: ' + $_.Exception.Message)
    }
}

function Handle-Goto($slideNum) {
    $ppt = Safe-GetPPT
    if ($null -eq $ppt) {
        return 'ERROR:PowerPoint is not currently running.'
    }
    try {
        if ($null -eq $ppt.Presentations -or $ppt.Presentations.Count -eq 0) {
            return 'ERROR:No presentation is open in PowerPoint.'
        }
    } catch {
        return 'ERROR:PowerPoint is busy or blocked by a modal dialog.'
    }

    try {
        Ensure-SlideShow $ppt
        $sIdx = [int]$slideNum
        if ($ppt.SlideShowWindows.Count -gt 0) {
            $ppt.SlideShowWindows.Item(1).View.GotoSlide($sIdx)
            return ('OK:Jumped to slide ' + $sIdx)
        } elseif ($ppt.ActiveWindow -and $ppt.ActiveWindow.View) {
            $ppt.ActiveWindow.View.GotoSlide($sIdx)
            return ('OK:Jumped to slide ' + $sIdx)
        }
        return 'ERROR:Slide show window is not available.'
    } catch {
        return ('ERROR:Failed jumping to slide: ' + $_.Exception.Message)
    }
}

function Handle-Next {
    $ppt = Safe-GetPPT
    if ($null -eq $ppt) {
        return 'ERROR:PowerPoint is not currently running.'
    }
    try {
        if ($null -eq $ppt.Presentations -or $ppt.Presentations.Count -eq 0) {
            return 'ERROR:No presentation is open in PowerPoint.'
        }
    } catch {
        return 'ERROR:PowerPoint is busy or blocked by a modal dialog.'
    }

    try {
        Ensure-SlideShow $ppt
        if ($ppt.SlideShowWindows.Count -gt 0) {
            $ppt.SlideShowWindows.Item(1).View.Next()
            return 'OK:Advanced to next slide.'
        } elseif ($ppt.ActiveWindow -and $ppt.ActiveWindow.View) {
            $cur = $ppt.ActiveWindow.View.Slide.SlideIndex
            $max = $ppt.ActivePresentation.Slides.Count
            if ($cur -lt $max) {
                $ppt.ActiveWindow.View.GotoSlide($cur + 1)
            }
            return 'OK:Advanced to next slide.'
        }
        return 'ERROR:Slide show window is not available.'
    } catch {
        return ('ERROR:Failed advancing slide: ' + $_.Exception.Message)
    }
}

function Handle-Prev {
    $ppt = Safe-GetPPT
    if ($null -eq $ppt) {
        return 'ERROR:PowerPoint is not currently running.'
    }
    try {
        if ($null -eq $ppt.Presentations -or $ppt.Presentations.Count -eq 0) {
            return 'ERROR:No presentation is open in PowerPoint.'
        }
    } catch {
        return 'ERROR:PowerPoint is busy or blocked by a modal dialog.'
    }

    try {
        Ensure-SlideShow $ppt
        if ($ppt.SlideShowWindows.Count -gt 0) {
            $ppt.SlideShowWindows.Item(1).View.Previous()
            return 'OK:Returned to previous slide.'
        } elseif ($ppt.ActiveWindow -and $ppt.ActiveWindow.View) {
            $cur = $ppt.ActiveWindow.View.Slide.SlideIndex
            if ($cur -gt 1) {
                $ppt.ActiveWindow.View.GotoSlide($cur - 1)
            }
            return 'OK:Returned to previous slide.'
        }
        return 'ERROR:Slide show window is not available.'
    } catch {
        return ('ERROR:Failed returning to previous slide: ' + $_.Exception.Message)
    }
}

while ($true) {
    $line = $stdin.ReadLine()
    if ($null -eq $line -or $line -eq '__EXIT__') { break }
    if ($line -eq '__PING__') {
        $stdout.WriteLine('OK:PONG')
        continue
    }
    $parts = $line.Split('|', 3)
    $cmd = $parts[0]
    $res = 'ERROR:Unknown command'
    if ($cmd -eq 'OPEN') {
        $slideArg = if ($parts.Length -gt 2) { $parts[2] } else { '1' }
        $res = Handle-Open $parts[1] $slideArg
    } elseif ($cmd -eq 'GOTO') {
        $slideArg = if ($parts.Length -gt 1) { $parts[1] } else { '1' }
        $res = Handle-Goto $slideArg
    } elseif ($cmd -eq 'NEXT') {
        $res = Handle-Next
    } elseif ($cmd -eq 'PREV') {
        $res = Handle-Prev
    } elseif ($cmd -eq 'START') {
        $res = Handle-Start
    }
    $stdout.WriteLine($res)
}
