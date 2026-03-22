param(
    [int]$Port = 7777,
    [string]$RuleName = "Pseudo-OnBlivion Relay"
)

$existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if (-not $existing) {
    New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow | Out-Null
    Write-Output "Created firewall rule '$RuleName' for TCP port $Port"
} else {
    Write-Output "Firewall rule '$RuleName' already exists"
}
