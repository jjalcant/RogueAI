$desktop = "C:\Users\Jhonn\OneDrive\Desktop"

Get-ChildItem $desktop -File | ForEach-Object {
    $name = $_.Name
    $ext = $_.Extension.ToLower()

    if ($ext -in ".jpg",".jpeg",".png",".gif",".webp",".bmp") {
        Move-Item $_.FullName "$desktop\Images"
    }
    elseif ($ext -in ".doc",".docx",".pdf",".txt",".html") {
        Move-Item $_.FullName "$desktop\Documents"
    }
    elseif ($ext -in ".exe",".dll",".node") {
        Move-Item $_.FullName "$desktop\Programs"
    }
    elseif ($ext -in ".lnk",".url") {
        Move-Item $_.FullName "$desktop\Shortcuts"
    }
    elseif ($ext -in ".mp3",".wav",".ogg",".aac") {
        Move-Item $_.FullName "$desktop\Audio"
    }
    elseif ($ext -in ".sql",".json") {
        Move-Item $_.FullName "$desktop\Code"
    }
    else {
        Move-Item $_.FullName "$desktop\Other"
    }
}