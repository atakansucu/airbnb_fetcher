# Airbnb Monitoring Workflow

## Overview
This project is designed to monitor Airbnb listings for new entries, price drops, and rare deals. It utilizes GitHub Actions to automate the monitoring process, sending notifications via Telegram for significant events.

## Project Structure
```
airbnb-monitoring-workflow
├── .github
│   └── workflows
│       └── airbnb-monitor.yml
├── src
│   ├── monitor.js
│   ├── notifications.js
│   ├── logger.js
│   └── utils
│       └── storage.js
├── package.json
├── playwright.config.js
└── README.md
```

## Setup Instructions

1. **Clone the Repository**
   ```bash
   git clone <repository-url>
   cd airbnb-monitoring-workflow
   ```

2. **Install Dependencies**
   Ensure you have Node.js installed, then run:
   ```bash
   npm install
   ```

3. **Configure GitHub Secrets**
   In your GitHub repository, navigate to `Settings` > `Secrets and variables` > `Actions` and add the following secrets:
   - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token.
   - `TELEGRAM_CHAT_ID`: Your Telegram chat ID.

4. **Playwright Browsers Installation**
   The workflow will automatically install the necessary Playwright browsers during execution. Ensure that your workflow file includes the appropriate steps.

## GitHub Actions Workflow
The workflow is defined in `.github/workflows/airbnb-monitor.yml`. It is configured to:
- Run every 30 minutes using a cron schedule.
- Support manual triggers via `workflow_dispatch`.
- Install Playwright browsers.
- Execute the monitoring script.
- Send notifications for new listings, price drops, or rare deals.

## Manual Trigger
You can manually trigger the workflow from the GitHub Actions tab in your repository.

## Notifications
Notifications will be sent via Telegram for:
- New listings
- Price drops
- Rare deals

## Logging
The project includes robust logging functionality to track the monitoring process, ensuring that all significant events are logged appropriately.

## Conclusion
This Airbnb monitoring workflow automates the process of tracking listings and provides timely notifications, making it easier to stay updated on potential opportunities.