module.exports = {
  apps: [
    {
      name: "dev-news-bot",
      cwd: "/home/kali/discordbots/dev-news-bot",
      script: "bot.py",
      interpreter: "/home/kali/discordbots/dev-news-bot/.venv/bin/python",
      interpreter_args: "",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      min_uptime: "10s",
    },
  ],
};
