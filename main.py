import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes
import anthropic
from config import TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, WEBHOOK_URL, PORT, ENVIRONMENT
from picnic_client import add_ingredients_to_cart

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Anthropic client
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Conversation states
CONFIRMING, SELECTING = range(2)


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


async def extract_ingredients_from_text(recipe_text: str) -> list[dict]:
    """Call Claude to extract structured ingredient lists from recipe suggestion text."""
    extraction_prompt = (
        "The following text contains vegetarian recipe suggestions. "
        "Return ONLY a JSON array — no markdown, no explanation — where each element has "
        '{"recipe_name": "...", "ingredients": ["ingredient1", "ingredient2", ...]}. '
        "Use generic ingredient names without quantities or preparation methods "
        "(e.g. 'garlic' not '3 cloves of garlic, minced')."
    )
    message = claude_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        system=extraction_prompt,
        messages=[{"role": "user", "content": recipe_text}],
    )
    raw = "".join(block.text for block in message.content if hasattr(block, "text"))
    return json.loads(raw)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user messages and get recipe suggestions."""
    user_message = update.message.text
    user_id = update.effective_user.id

    logger.info(f"User {user_id}: {user_message}")

    await update.message.chat.send_action(action="typing")

    try:
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

        message = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            tools=[{"type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 5,
                    "allowed_domains": [
                        "miljuschka.nl",
                        "uitpaulineskeuken.nl"
                    ]}],
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        response_text = "".join(
            block.text for block in message.content if hasattr(block, 'text')
        )

        await update.message.reply_text(response_text)
        logger.info(f"Sent response to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error. Please try again later."
        )
        return ConversationHandler.END

    try:
        recipes = await extract_ingredients_from_text(response_text)
        context.user_data["recipes"] = recipes
    except Exception as e:
        logger.error(f"Ingredient extraction failed: {e}")
        return ConversationHandler.END

    recipe_list = "\n".join(f"{i+1}. {r['recipe_name']}" for i, r in enumerate(recipes))
    await update.message.reply_text(
        f"Would you like to add ingredients to your Picnic basket?\n\n"
        f"Reply with the number of the recipe you'd like to shop for, or 'no' to skip.\n\n"
        f"{recipe_list}"
    )
    return CONFIRMING


async def confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle recipe selection after recipes are suggested."""
    text = update.message.text.strip().lower()

    if text == "no":
        await update.message.reply_text("No problem! Let me know whenever you want more recipe ideas.")
        return ConversationHandler.END

    recipes = context.user_data.get("recipes", [])
    try:
        choice = int(text) - 1
        if not (0 <= choice < len(recipes)):
            raise ValueError
    except ValueError:
        names = "\n".join(f"{i+1}. {r['recipe_name']}" for i, r in enumerate(recipes))
        await update.message.reply_text(
            f"Please reply with a number between 1 and {len(recipes)}, or 'no'.\n\n{names}"
        )
        return CONFIRMING

    selected = recipes[choice]
    context.user_data["selected_recipe"] = selected
    ingredient_list = ", ".join(selected["ingredients"])

    await update.message.reply_text(
        f"I'll add the ingredients for *{selected['recipe_name']}* to your Picnic basket:\n\n"
        f"{ingredient_list}\n\n"
        f"Confirm? (yes / no)",
        parse_mode="Markdown"
    )
    return SELECTING


async def selecting_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle final confirmation before adding to Picnic cart."""
    text = update.message.text.strip().lower()

    if text != "yes":
        await update.message.reply_text("Cancelled. Let me know if you want recipe ideas!")
        return ConversationHandler.END

    selected = context.user_data.get("selected_recipe", {})
    ingredients = selected.get("ingredients", [])

    await update.message.chat.send_action(action="typing")

    result = add_ingredients_to_cart(ingredients)

    added_lines = "\n".join(
        f"- {item['ingredient']} → {item['product_name']}" for item in result["added"]
    )
    reply = f"Added to your Picnic basket:\n{added_lines}"

    if result["not_found"]:
        not_found_lines = "\n".join(f"- {i}" for i in result["not_found"])
        reply += f"\n\nNot found on Picnic:\n{not_found_lines}"

    await update.message.reply_text(reply)
    return ConversationHandler.END


def main():
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        states={
            CONFIRMING: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_handler)],
            SELECTING:  [MessageHandler(filters.TEXT & ~filters.COMMAND, selecting_handler)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    application.add_handler(conv_handler)

    if ENVIRONMENT == 'production' and WEBHOOK_URL:
        logger.info(f"Starting webhook on port {PORT}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            allowed_updates=Update.ALL_TYPES
        )
    else:
        logger.info("Starting polling mode (development)")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
