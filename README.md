# NX Pipeline Dashboard

## Control
- Start Webserver
```
.\web\start_dashboard.ps1 -Port 
```

- Bypass-ExecutionPolicy
```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

- Run checks
```
.\ops\run_checks.ps1 `
>>     -RootParts "C:\BRS-Nextcloud\CAD_Space\G26" `
>>     -Framework "C:\GitHub\nx-testframework\src" `
>>   -TimeoutMinutes 180
```