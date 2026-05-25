/**
 * PM2 配置：poly-trader 服务（Flask 8000 + MCP 8001）
 * 断线/崩溃自动重启，指数退避防抖动
 */
module.exports = {
  apps: [
    {
      name: "poly-trader",
      script: "main.py",
      cwd: __dirname,
      interpreter: __dirname + "/.venv/bin/python",
      interpreter_args: "-u",
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 50,
      min_uptime: "5s",
      restart_delay: 2000,
      exp_backoff_restart_delay: 100,
      max_memory_restart: "500M",
      env: {},
      error_file: __dirname + "/logs/pm2-err.log",
      out_file: __dirname + "/logs/pm2-out.log",
      merge_logs: true,
      time: true,
    },
  ],
};
