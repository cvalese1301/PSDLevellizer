param (
    [string]$ImagePath
)

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { 
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
})[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null

if (-not $ImagePath -or -not (Test-Path $ImagePath)) {
    Write-Output "[]"
    exit 0
}

try {
    $fullPath = (Resolve-Path $ImagePath).Path
    $fileTask = [Windows.Storage.StorageFile]::GetFileFromPathAsync($fullPath)
    $file = Await $fileTask ([Windows.Storage.StorageFile])

    $streamTask = $file.OpenAsync([Windows.Storage.FileAccessMode]::Read)
    $stream = Await $streamTask ([Windows.Storage.Streams.IRandomAccessStream])

    $decoderTask = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)
    $decoder = Await $decoderTask ([Windows.Graphics.Imaging.BitmapDecoder])

    $bitmapTask = $decoder.GetSoftwareBitmapAsync()
    $bitmap = Await $bitmapTask ([Windows.Graphics.Imaging.SoftwareBitmap])

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if (-not $engine) {
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new("en-US"))
    }

    $ocrTask = $engine.RecognizeAsync($bitmap)
    $result = Await $ocrTask ([Windows.Media.Ocr.OcrResult])

    $lines = @()
    foreach ($line in $result.Lines) {
        $minX = 999999
        $minY = 999999
        $maxX = 0
        $maxY = 0

        foreach ($w in $line.Words) {
            if ($w.BoundingRect.X -lt $minX) { $minX = $w.BoundingRect.X }
            if ($w.BoundingRect.Y -lt $minY) { $minY = $w.BoundingRect.Y }
            $wRight = $w.BoundingRect.X + $w.BoundingRect.Width
            $wBottom = $w.BoundingRect.Y + $w.BoundingRect.Height
            if ($wRight -gt $maxX) { $maxX = $wRight }
            if ($wBottom -gt $maxY) { $maxY = $wBottom }
        }

        $lines += [PSCustomObject]@{
            Text = $line.Text
            X = [int]$minX
            Y = [int]$minY
            Width = [int]($maxX - $minX)
            Height = [int]($maxY - $minY)
        }
    }

    $lines | ConvertTo-Json -Compress
} catch {
    Write-Output "[]"
}
