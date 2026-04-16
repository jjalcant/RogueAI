$desktopPath = [Environment]::GetFolderPath("Desktop")

$extMap = @{
    Images    = @(".jpg",".jpeg",".png",".gif",".webp",".bmp")
    Documents = @(".doc",".docx",".pdf",".txt",".xlsx",".xls",".ppt",".pptx")
    Videos    = @(".mp4",".avi",".mov",".mkv",".wmv")
    Audio     = @(".mp3",".wav",".ogg",".aac",".flac")
    Archives  = @(".zip",".rar",".7z",".tar",".gz")
    Programs  = @(".exe",".msi")
}

$preview = @{
    Images    = @()
    Documents = @()
    Videos    = @()
    Audio     = @()
    Archives  = @()
    Programs  = @()
    Other     = @()
}

Get-ChildItem -Path $desktopPath -File | ForEach-Object {

    if ($_.Extension -eq ".lnk") { return }

    $ext = $_.Extension.ToLower()
    $matched = $false

    foreach ($cat in $extMap.Keys) {

        if ($extMap[$cat] -contains $ext) {

            $preview[$cat] += $_.Name
            $matched = $true
            break
        }

    }

    if (-not $matched) {

        $preview["Other"] += $_.Name

    }

}

foreach ($cat in $preview.Keys) {

    Write-Host "`n[$cat]"

    if ($preview[$cat].Count -eq 0) {

        Write-Host "  (none)"

    }

    else {

        $preview[$cat] | ForEach-Object {

            Write-Host "  $_"

        }

    }

}