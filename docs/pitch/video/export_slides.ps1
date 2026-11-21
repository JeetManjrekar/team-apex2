# Renders deck slides 2-4 (story, gap, solution) to a 1080p30 MP4 with Morph + animations, using PowerPoint itself.
# Click builds become timed builds so they land on the voiceover lines. Usage: powershell -File export_slides.ps1
param(
  [string]$Deck = "$PSScriptRoot\raw\deck_segoe.pptx",
  [string]$Out  = "$PSScriptRoot\raw\slides_2-4.mp4",
  # seconds each kept slide stays up; story builds fire at the given offsets (s from slide start)
  [double[]]$Durations = @(12.0, 6.0, 7.0),
  [double[]]$StoryClicks = @(3.2, 6.4, 9.2)
)
$ErrorActionPreference = 'Stop'
$work = "$PSScriptRoot\raw\slides_work.pptx"
Copy-Item $Deck $work -Force
$pp = New-Object -ComObject PowerPoint.Application
try {
  $p = $pp.Presentations.Open($work, $false, $false, $false)   # ReadOnly=false, Untitled=false, WithWindow=false
  # keep slides 2,3,4 only (delete from the end so indices stay valid)
  for ($i = $p.Slides.Count; $i -ge 1; $i--) { if ($i -lt 2 -or $i -gt 4) { $p.Slides.Item($i).Delete() } }
  for ($i = 1; $i -le $p.Slides.Count; $i++) {
    $s = $p.Slides.Item($i)
    $seq = $s.TimeLine.MainSequence
    $clicks = 0; $last = 0.0
    for ($k = 1; $k -le $seq.Count; $k++) {
      $e = $seq.Item($k)
      if ($e.Timing.TriggerType -eq 1) {                 # msoAnimTriggerOnPageClick
        $clicks++
        $at = if ($i -eq 1 -and $clicks -le $StoryClicks.Count) { $StoryClicks[$clicks - 1] } else { 1.0 }
        $e.Timing.TriggerType = 2                        # msoAnimTriggerWithPrevious, timed from the slide start
        $e.Timing.TriggerDelayTime = $at
        $last = $at
      }
    }
    $t = $s.SlideShowTransition
    $t.AdvanceOnTime = -1; $t.AdvanceOnClick = 0; $t.AdvanceTime = $Durations[$i - 1]
    Write-Output ("slide {0}: {1} effects, {2} click builds retimed, {3}s" -f $i, $seq.Count, $clicks, $Durations[$i - 1])
  }
  $p.Save()
  if (Test-Path $Out) { Remove-Item $Out -Force }
  # CreateVideo(FileName, UseTimingsAndNarrations, DefaultSlideDuration, VertResolution, FramesPerSecond, Quality)
  $p.CreateVideo($Out, $true, 5, 1080, 30, 100)
  while ($p.CreateVideoStatus -eq 1 -or $p.CreateVideoStatus -eq 2) { Start-Sleep -Milliseconds 800 }   # InProgress / Queued
  Write-Output ("CreateVideoStatus = {0} (3 = done)" -f $p.CreateVideoStatus)
  $p.Close()
} finally {
  $pp.Quit(); [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
}
