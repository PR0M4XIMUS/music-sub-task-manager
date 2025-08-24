# 🎵 Subs Tasks Manager Bot

A modern Telegram bot designed to streamline shared subscription management with automated payment tracking, proof collection, and smart monthly reminders featuring an intuitive visual interface.

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Prerequisites](#-prerequisites)  
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Development](#-development)
- [Contributing](#-contributing)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

## 🎯 Overview

This Telegram bot helps groups manage shared subscription payments efficiently by:
- Tracking who has paid and when
- Collecting payment proofs automatically
- Sending intelligent reminders
- Providing visual dashboards for admins
- Maintaining payment history and analytics

Perfect for managing subscriptions like Netflix, Spotify, YouTube Premium, or any shared service where multiple people contribute monthly payments.

## ✨ Features

### 🎯 Visual Interface
- **Interactive buttons** for all commands - no more typing!
- **Quick payment options** with preset amounts (1, 3, 6 months)
- **Visual menus** for easy navigation
- **Enhanced messages** with emojis and clear formatting
- **Admin dashboard** with organized button controls

### 👥 User Features
- **`/start`** - Welcome screen with quick action buttons
- **`/pay <amount> <months>`** - Payment with visual confirmation and buttons
- **`/history`** - Payment history with summary and quick actions
- **`/help`** - Interactive help with action buttons
- **Photo/Document upload** - Seamless proof submission after payment

### 🔧 Admin Features  
- **`/status`** - User payment status with visual formatting
- **`/setmute <user> <months>`** - Mute reminders with confirmation
- **`/setamount <value>`** - Set monthly amount
- **`/setday <1-28>`** - Set billing day
- **`/proof <user>`** - Fetch payment proof with user info
- **`/addmember <user>`** - Add members with guidance
- **`/remove <user>`** - Remove users and data  
- **`/export`** - CSV export with enhanced formatting

### 🤖 Smart Features
- **Visual reminders** with quick payment buttons
- **Payment summaries** in history view
- **Error handling** with helpful suggestions
- **Admin/user role detection** with appropriate menus
- **Quick actions** available from every screen

### 🎨 UI Improvements
- 🎵 Welcome messages with context-appropriate menus
- 💳 Payment flow with visual confirmation steps
- 📊 Enhanced data presentation with summaries
- 🔧 Admin interface organized by function
- ⏰ Interactive reminders with one-click payments
- 💡 Helpful tips and clear instructions throughout

## 🔧 Prerequisites

Before setting up the bot, ensure you have:

- **Python 3.9+** (recommended: Python 3.11)
- **Telegram Bot Token** from [@BotFather](https://t.me/BotFather)
- **Your Telegram User ID** (get it from [@userinfobot](https://t.me/userinfobot))
- **Docker** (optional, for containerized deployment)

## 🚀 Installation

### Method 1: Local Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/PR0M4XIMUS/music-sub-task-manager.git
   cd music-sub-task-manager
   ```

2. **Create virtual environment** (recommended)
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/macOS
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables** (see [Configuration](#-configuration))

5. **Run the bot**
   ```bash
   python bot.py
   ```

### Method 2: Docker Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/PR0M4XIMUS/music-sub-task-manager.git
   cd music-sub-task-manager
   ```

2. **Create environment file**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Run with Docker Compose**
   ```bash
   docker-compose up -d
   ```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Required Variables
BOT_TOKEN=your_bot_token_from_botfather
ADMIN_ID=your_telegram_user_id

# Optional Variables (with defaults)
MONTHLY_AMOUNT=2.50              # Default monthly subscription cost
BILLING_DAY=1                    # Day of month for billing (1-28)
TIMEZONE=Europe/Chisinau         # Timezone for reminders
REMINDER_HOUR=10                 # Hour of day to send reminders (0-23)
```

### Getting Your Bot Token

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Choose a name and username for your bot
4. Copy the token provided

### Finding Your User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Forward any message to it, or send `/start`
3. Copy your User ID number

### Configuration Details

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `BOT_TOKEN` | Telegram bot token from BotFather | - | ✅ |
| `ADMIN_ID` | Telegram user ID of the admin | - | ✅ |
| `MONTHLY_AMOUNT` | Default monthly subscription amount | `2.50` | ❌ |
| `BILLING_DAY` | Day of month for billing cycle (1-28) | `1` | ❌ |
| `TIMEZONE` | Timezone for scheduled reminders | `Europe/Chisinau` | ❌ |
| `REMINDER_HOUR` | Hour of day to send reminders (24h format) | `10` | ❌ |

## 📱 Usage

### Initial Setup

1. **Start the bot** by sending `/start` to your bot in Telegram
2. **Add members** using `/addmember @username` or `/addmember user_id`
3. **Configure settings** using admin commands like `/setamount` and `/setday`

### For Regular Users

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Show welcome screen with quick actions | `/start` |
| `/pay <amount> <months>` | Begin payment process | `/pay 7.50 3` |
| `/history` | View your payment history | `/history` |
| `/help` | Show available commands and tips | `/help` |

**Payment Process:**
1. Use `/pay <amount> <months>` or click "Make Payment" 
2. Select preset amounts (1, 3, 6 months) or enter custom amount
3. Upload payment proof (screenshot, receipt, etc.)
4. Confirmation message will appear

### For Administrators

#### User Management
| Command | Description | Example |
|---------|-------------|---------|
| `/addmember <user>` | Add new member to track | `/addmember @john` |
| `/remove <user>` | Remove member and their data | `/remove @john` |
| `/setmute <user> <months>` | Mute reminders for user | `/setmute @john 2` |

#### System Configuration
| Command | Description | Example |
|---------|-------------|---------|
| `/setamount <value>` | Set monthly subscription cost | `/setamount 5.99` |
| `/setday <1-28>` | Set billing day of month | `/setday 15` |

#### Monitoring & Reports  
| Command | Description | Example |
|---------|-------------|---------|
| `/status` | View all users' payment status | `/status` |
| `/proof <user>` | Get user's latest payment proof | `/proof @john` |
| `/export` | Export all payments to CSV | `/export` |

### Interactive Features

The bot provides **interactive buttons** for most actions:
- **Main Menu**: Quick access to payment, history, and help
- **Admin Dashboard**: Organized controls for user management and settings
- **Payment Flow**: Visual confirmation steps with preset amount buttons
- **Quick Actions**: Available from most screens for easy navigation

## 🛠️ Development

### Setting Up Development Environment

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/your-username/music-sub-task-manager.git
   cd music-sub-task-manager
   ```

2. **Install development dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

3. **Create test environment**
   ```bash
   cp .env.example .env
   # Add your test bot token and user ID
   ```

4. **Initialize database**
   ```bash
   python -c "
   import asyncio
   import database as db
   asyncio.run(db.init_db())
   print('✅ Database initialized!')
   "
   ```

### Project Structure

```
music-sub-task-manager/
├── bot.py              # Main bot application
├── database.py         # Database operations and models
├── utils.py           # Helper functions and utilities
├── scheduler.py       # Reminder scheduling logic
├── requirements.txt   # Python dependencies
├── Dockerfile        # Container configuration
├── docker-compose.yml # Docker deployment setup
├── .env.example      # Environment variables template
└── README.md         # Documentation (this file)
```

### Key Components

- **`bot.py`**: Main application with command handlers and UI logic
- **`database.py`**: SQLite database operations for users and payments
- **`utils.py`**: Date calculations, formatting, and parsing utilities
- **`scheduler.py`**: Automated reminder system using APScheduler

### Testing

Test the bot functionality:

```bash
# Validate imports and initialization
python -c "
import os
os.environ['BOT_TOKEN'] = '1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk'
os.environ['ADMIN_ID'] = '123456'
import bot
print('✅ Bot imports and initializes successfully!')
"

# Test database operations
python -c "
import asyncio
import database as db
async def test():
    await db.init_db()
    print('✅ Database operations working!')
asyncio.run(test())
"
```

## 🤝 Contributing

We welcome contributions! Here's how to get started:

### Development Workflow

1. **Fork the repository** on GitHub
2. **Create a feature branch** from `main`
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** following the coding standards
4. **Test thoroughly** with a test bot
5. **Commit with clear messages**
   ```bash
   git commit -m "feat: add payment reminder customization"
   ```
6. **Push to your fork** and create a Pull Request

### Coding Standards

- **Python**: Follow PEP 8 style guidelines
- **Comments**: Document complex functions and business logic
- **Error Handling**: Use appropriate try/catch blocks
- **UI Text**: Keep messages clear, concise, and user-friendly
- **Security**: Never commit tokens, credentials, or sensitive data

### Types of Contributions

- 🐛 **Bug Fixes**: Fix existing functionality issues
- ✨ **New Features**: Add new commands or capabilities  
- 🎨 **UI Improvements**: Enhance user interface and experience
- 📚 **Documentation**: Improve guides and code documentation
- 🔧 **DevOps**: Improve deployment and development workflow
- 🧪 **Testing**: Add tests for existing or new functionality

### Pull Request Guidelines

- **Clear Description**: Explain what your PR does and why
- **Screenshots**: Include UI changes screenshots if applicable
- **Testing**: Describe how you tested your changes
- **Breaking Changes**: Clearly note any breaking changes
- **Issue Reference**: Link to related issues if applicable

### Code Review Process

1. Automated checks must pass
2. At least one maintainer review required
3. All conversations must be resolved
4. No merge conflicts with main branch

## 🔍 Troubleshooting

### Common Issues

#### Bot Doesn't Start
```
Error: BOT_TOKEN and ADMIN_ID must be set via environment variables.
```
**Solution**: Ensure `.env` file exists with correct `BOT_TOKEN` and `ADMIN_ID`

#### Database Errors
```
sqlite3.OperationalError: no such table: users
```
**Solution**: Initialize the database:
```bash
python -c "import asyncio; import database as db; asyncio.run(db.init_db())"
```

#### Permission Errors
```
Error: This command requires admin privileges
```
**Solution**: Verify your `ADMIN_ID` matches your Telegram user ID

#### Timezone Issues
```
Reminders sent at wrong time
```
**Solution**: Set correct `TIMEZONE` in `.env` file (e.g., `America/New_York`)

### Docker Issues

#### Container Won't Start
```bash
# Check container logs
docker-compose logs subs_tasks_manager_bot

# Rebuild if needed
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

#### Volume Mount Issues
```bash
# Ensure data directory exists
mkdir -p ./data
chmod 755 ./data
```

### Getting Help

If you encounter issues:

1. **Check this troubleshooting section**
2. **Search existing GitHub Issues**
3. **Create a new Issue** with:
   - Clear description of the problem
   - Steps to reproduce
   - Error messages (if any)
   - Environment details (OS, Python version, etc.)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [aiogram](https://docs.aiogram.dev/) - Modern Telegram Bot framework
- Scheduling powered by [APScheduler](https://apscheduler.readthedocs.io/)
- Database operations using [aiosqlite](https://aiosqlite.omnilib.dev/)
- Thanks to all contributors who help improve this bot

---

⭐ **Star this repository** if you find it useful!

For support or questions, please [open an issue](https://github.com/PR0M4XIMUS/music-sub-task-manager/issues) on GitHub.

