param([Parameter(Mandatory=$true)][string]$TextPath, [Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voice.Rate = -1
    $voice.SetOutputToWaveFile($OutputPath)
    $voice.Speak([System.IO.File]::ReadAllText($TextPath))
} finally {
    $voice.Dispose()
}
