$ErrorActionPreference = 'Stop'
$dir = 'c:\Users\gamin\BoschAI\BoschAI\aios-starter-kit\outputs\branding\realistic-set'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$base = 'https://d8j0ntlcm91z4.cloudfront.net/user_3DXjOYWKPrC9KY6n3F2ZUQIveUp/'
$files = [ordered]@{
  '1-calm-command-center.png'  = 'hf_20260623_193612_957f1788-178f-403f-a76b-448f440c577e.png'
  '2-soft-central-hub.png'     = 'hf_20260623_193613_52b51741-c8d2-48ad-94c8-8f4b03796408.png'
  '3-quiet-nervous-system.png' = 'hf_20260623_193615_abb76f9d-c435-4ff2-8b5a-02dda60c3fd4.png'
  '4-empty-chair.png'          = 'hf_20260623_193617_0b2105e1-1387-4e03-8302-f473d7b66c96.png'
  '5-architectural-core.png'   = 'hf_20260623_193619_4933f1e0-05a9-4802-8aa4-3e7d00bf501e.png'
  '6-founder-at-peace.png'     = 'hf_20260623_193621_c49d4da9-ff9c-4088-b97e-199d06cbf822.png'
}
foreach ($name in $files.Keys) {
  Invoke-WebRequest -Uri ($base + $files[$name]) -OutFile (Join-Path $dir $name)
}
Get-ChildItem $dir | Select-Object Name, @{N='KB';E={[int]($_.Length/1KB)}} | Format-Table -AutoSize
