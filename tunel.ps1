# Mantiene el túnel vivo y deja la URL escrita en url-publica.txt
# Uso:  .\tunel.ps1        (dejá esta ventana abierta)

$ErrorActionPreference = "Continue"
$archivo = Join-Path $PSScriptRoot "url-publica.txt"

while ($true) {
  Write-Host "`n== Abriendo el tunel ==" -ForegroundColor Cyan
  $log = Join-Path $env:TEMP "hilo-tunel.log"
  if (Test-Path $log) { Remove-Item $log -Force }

  $p = Start-Process -FilePath "cloudflared" `
        -ArgumentList "tunnel","--url","http://localhost:8000","--no-autoupdate" `
        -RedirectStandardError $log -NoNewWindow -PassThru

  # esperamos a que Cloudflare escupa la direccion
  $url = $null
  for ($i = 0; $i -lt 40 -and -not $url; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
      $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
      if ($m) { $url = $m.Matches[0].Value }
    }
  }

  if ($url) {
    Set-Content -Path $archivo -Value $url -Encoding ascii
    Write-Host "`n  LA APP ESTA EN:  $url" -ForegroundColor Green
    Write-Host "  (guardada en url-publica.txt)`n"
  } else {
    Write-Host "  No pude leer la URL. Mira $log" -ForegroundColor Yellow
  }

  Wait-Process -Id $p.Id
  Write-Host "`n!! El tunel se cayo. Lo levanto de nuevo en 3 segundos." -ForegroundColor Yellow
  Write-Host "   OJO: la URL nueva va a ser distinta." -ForegroundColor Yellow
  Start-Sleep -Seconds 3
}
