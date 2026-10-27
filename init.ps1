<#
.SYNOPSIS
    RootTrace Initialization Entrypoint (Root Shortcut)
.DESCRIPTION
    Forwards execution to scripts/init.ps1 with all supplied parameters.
#>

[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$SkipOllama
)

$ScriptPath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "scripts\init.ps1"
& $ScriptPath @PSBoundParameters
