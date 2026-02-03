import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from config import TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, WEBHOOK_URL, PORT, ENVIRONMENT

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Anthropic client
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "Hi! I'm your Picnic grocery assistant. 🛒\n\n"
        "Tell me what ingredients you have, and I'll suggest some recipes!\n\n"
        "Example: 'I have chicken, rice, onions, and tomatoes'"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Just tell me what ingredients you have available, and I'll suggest recipes you can make!\n\n"
        "Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages and get recipe suggestions."""
    user_message = update.message.text
    user_id = update.effective_user.id
    
    logger.info(f"User {user_id}: {user_message}")
    
    # Send "thinking" indicator
    await update.message.chat.send_action(action="typing")
    
    try:
        # Create prompt for Claude
        system_prompt = """You are a helpful cooking assistant. When users tell you what ingredients they have, 
        suggest 5 vegetarian recipes they could make. Find the recipes on the following websites and their subdomains.
        - https://miljuschka.nl/
        - https://uitpaulineskeuken.nl
         
        In your message to the user you should include for each recipe:
        - Recipe name
        - Brief description (1 sentence)
        - Estimated cooking time
        - URL to the recipe (you have to be sure that the URL is correct and exists)
        
        Keep suggestions practical and realistic. Format your response in a clear, readable way."""
        
        # Call Claude API
        message = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            tools=[{"type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 5,
                    "allowed_domains": [
                        "https://miljuschka.nl",
                        "https://uitpaulineskeuken.nl"
                    ]}],
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        
        # response_text = message.content[0].text
        response_text = "".join(
            block.text for block in message.content if hasattr(block, 'text')
        )
        
        # Send response to user
        await update.message.reply_text(response_text)
        
        logger.info(f"Sent response to user {user_id}")
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error. Please try again later."
        )

def main():
    """Start the bot."""
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    if ENVIRONMENT == 'production' and WEBHOOK_URL:
        # Production: use webhook
        logger.info(f"Starting webhook on port {PORT}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            allowed_updates=Update.ALL_TYPES
        )
    else:
        # Development: use polling
        logger.info("Starting polling mode (development)")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()