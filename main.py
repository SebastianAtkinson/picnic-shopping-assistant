import html
import json
import logging
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
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
ASKING, CHOOSING, CONFIRMING, SELECTING_INGREDIENTS = range(4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send a message when the command /start is issued."""
    await update.message.reply_text("Welke ingrediënten heb je beschikbaar?")
    return ASKING


async def ask_for_ingredients(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for any text message — prompt for ingredients."""
    await update.message.reply_text("Welke ingrediënten heb je beschikbaar?")
    return ASKING


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Vertel me welke ingrediënten je hebt en ik stel recepten voor die je kunt maken!\n\n"
        "Commando's:\n"
        "/start - Start de bot\n"
        "/help - Toon dit helpbericht"
    )


async def extract_recipe_data(recipe_text: str) -> list[dict]:
    """Extract structured recipe data (name, cooking time, URL, ingredients) from Claude's response."""
    extraction_prompt = (
        "The following text contains vegetarian recipe suggestions from Dutch cooking websites. "
        "Return ONLY a JSON array — no markdown, no explanation — where each element has: "
        '{"recipe_name": "...", "cooking_time": "...", "url": "...", "ingredients": ["ingredient1", ...]}. '
        "For 'cooking_time' use a short string like '30 min'. "
        "For 'url' include the exact URL from the text. "
        "For 'ingredients' list 4-6 main generic ingredient names without quantities "
        "(e.g. 'garlic' not '3 cloves of garlic, minced')."
    )
    message = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        system=extraction_prompt,
        messages=[{"role": "user", "content": recipe_text}],
    )
    logger.info(f"Extraction — input: {message.usage.input_tokens}, output: {message.usage.output_tokens}")
    raw = "".join(block.text for block in message.content if hasattr(block, "text"))
    # Strip markdown code fences if the model wraps the JSON despite the instruction
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw.strip())
    return json.loads(raw)


def _format_recipe_cards(recipes: list[dict]) -> str:
    """Format recipes as structured HTML cards."""
    cards = []
    for i, recipe in enumerate(recipes, 1):
        name = html.escape(recipe['recipe_name'])
        lines = [f"<b>{i}. {name}</b>"]
        if recipe.get("cooking_time"):
            lines.append(f"⏱ {html.escape(recipe['cooking_time'])}")
        if recipe.get("ingredients"):
            lines.append(f"🥕 {html.escape(', '.join(recipe['ingredients'][:5]))}")
        if recipe.get("url"):
            url = html.escape(recipe["url"])
            lines.append(f'<a href="{url}">Bekijk recept →</a>')
        cards.append("\n".join(lines))
    return "\n\n".join(cards)


def _build_selection_keyboard(recipes: list[dict], selected: set) -> InlineKeyboardMarkup:
    """Build toggle keyboard for recipe multi-selection."""
    rows = []
    for i, recipe in enumerate(recipes):
        mark = "✅" if i in selected else "☐"
        rows.append([InlineKeyboardButton(
            f"{mark} {recipe['recipe_name']}",
            callback_data=f"toggle_{i}",
        )])
    rows.append([
        InlineKeyboardButton("🛒 Toevoegen aan Picnic", callback_data="add_selected"),
        InlineKeyboardButton("✕ Overslaan", callback_data="recipe_no"),
    ])
    return InlineKeyboardMarkup(rows)


def _build_ingredient_keyboard(ingredients: list[str], selected: set) -> InlineKeyboardMarkup:
    """Build toggle keyboard for ingredient subset selection."""
    rows = []
    for i, ing in enumerate(ingredients):
        mark = "✅" if i in selected else "☐"
        rows.append([InlineKeyboardButton(
            f"{mark} {ing}",
            callback_data=f"ing_toggle_{i}",
        )])
    rows.append([
        InlineKeyboardButton("🛒 Toevoegen aan Picnic", callback_data="ing_confirm"),
        InlineKeyboardButton("✕ Annuleren", callback_data="ing_cancel"),
    ])
    return InlineKeyboardMarkup(rows)


def _format_cart_result(selected_recipes: list[dict], result: dict, chosen_ingredients: list[str] | None = None) -> str:
    """Format the cart result as HTML."""
    added_map = {item["ingredient"].lower(): item["product_name"] for item in result["added"]}

    recipe_sections = []
    for recipe in selected_recipes:
        name = recipe["recipe_name"]
        url = recipe.get("url", "")
        header = f'<b><a href="{url}">{name}</a></b>' if url else f"<b>{name}</b>"
        lines = []
        for ing in recipe.get("ingredients", []):
            if chosen_ingredients is not None and ing not in chosen_ingredients:
                continue
            product = added_map.get(ing.lower())
            if product:
                lines.append(f"  - {ing} → {product}")
        if lines:
            recipe_sections.append(header + "\n" + "\n".join(lines))

    reply = "Toegevoegd aan je Picnic mandje:\n\n" + "\n\n".join(recipe_sections)
    if result["not_found"]:
        not_found_lines = "\n".join(f"- {i}" for i in result["not_found"])
        reply += f"\n\nNiet gevonden op Picnic:\n{not_found_lines}"

    return reply


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user messages and get recipe suggestions."""
    user_message = update.message.text
    user_id = update.effective_user.id

    logger.info(f"User {user_id}: {user_message}")

    context.user_data["user_ingredients_text"] = user_message.lower()
    loading_msg = await update.message.reply_text("⏳ Even geduld, ik zoek recepten voor je...")

    try:
        system_prompt = """Je bent een behulpzame kookassistent. Als gebruikers vertellen welke ingrediënten ze hebben,
        stel je 3 vegetarische recepten voor die ze kunnen maken. Zoek de recepten op de volgende websites en hun subdomeinen.
        - https://miljuschka.nl/
        - https://uitpaulineskeuken.nl

        Houd rekening met eventuele wensen of voorkeuren die de gebruiker heeft meegegeven, zoals:
        - Type keuken of gerecht (bijv. Italiaans, soep, pasta)
        - Bereidingstijd (bijv. snel, onder 30 minuten)
        - Speciale dieetwensen of smaken
        Verwerk deze voorkeuren in je receptsuggesties.

        Geef voor elk recept:
        - Receptnaam
        - Korte beschrijving (1 zin)
        - Geschatte bereidingstijd
        - URL naar het recept (zorg ervoor dat de URL correct is en bestaat)

        Houd de suggesties praktisch en realistisch. Antwoord altijd in het Nederlands."""

        message = claude_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=system_prompt,
            tools=[{"type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 3,
                    "allowed_domains": [
                        "miljuschka.nl",
                        "uitpaulineskeuken.nl"
                    ]}],
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        logger.info(f"Recipe search — input: {message.usage.input_tokens}, output: {message.usage.output_tokens}")
        response_text = "".join(
            block.text for block in message.content if hasattr(block, 'text')
        )

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await loading_msg.edit_text("Sorry, er is een fout opgetreden. Probeer het later opnieuw.")
        return ConversationHandler.END

    try:
        recipes = await extract_recipe_data(response_text)
        context.user_data["recipes"] = recipes
        context.user_data["selected_indices"] = set()

        cards = _format_recipe_cards(recipes)
        keyboard = _build_selection_keyboard(recipes, set())

        await loading_msg.edit_text(
            cards + "\n\n<i>Selecteer de recepten die je aan je Picnic mandje wilt toevoegen:</i>",
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        return CHOOSING

    except Exception as e:
        logger.error(f"Recipe extraction failed: {e}")
        await loading_msg.edit_text(response_text)
        return ConversationHandler.END


async def toggle_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle a recipe's selection state."""
    query = update.callback_query
    await query.answer()

    index = int(query.data.split("_")[1])
    selected: set = context.user_data.get("selected_indices", set())

    if index in selected:
        selected.discard(index)
    else:
        selected.add(index)
    context.user_data["selected_indices"] = selected

    recipes = context.user_data.get("recipes", [])
    await query.edit_message_reply_markup(
        reply_markup=_build_selection_keyboard(recipes, selected)
    )
    return CHOOSING


async def add_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show confirmation screen with ingredient choice for the selected recipes."""
    query = update.callback_query

    selected: set = context.user_data.get("selected_indices", set())
    if not selected:
        await query.answer("Selecteer eerst minimaal één recept.", show_alert=True)
        return CHOOSING

    await query.answer()
    recipes = context.user_data.get("recipes", [])
    selected_recipes = [recipes[i] for i in sorted(selected)]
    context.user_data["selected_recipes"] = selected_recipes

    user_ingredients_text = context.user_data.get("user_ingredients_text", "")

    seen: set = set()
    all_ingredients: list[str] = []
    for recipe in selected_recipes:
        for ing in recipe.get("ingredients", []):
            key = ing.lower()
            if key in seen:
                continue
            seen.add(key)
            # Skip ingredients the user indicated they already have
            if any(word in user_ingredients_text for word in key.split()):
                continue
            all_ingredients.append(ing)

    context.user_data["all_ingredients"] = all_ingredients

    recipe_names = "\n".join(f"• {r['recipe_name']}" for r in selected_recipes)
    ingredient_list = ", ".join(all_ingredients)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✓ Alle ingrediënten toevoegen", callback_data="confirm_all")],
        [InlineKeyboardButton("☑ Kies ingrediënten", callback_data="confirm_choose")],
        [InlineKeyboardButton("✕ Annuleren", callback_data="confirm_no")],
    ])

    await query.edit_message_text(
        f"Ingrediënten voor:\n{recipe_names}\n\n"
        f"<b>Ingrediënten:</b> {ingredient_list}\n\n"
        f"Wat wil je doen?",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    return CONFIRMING


async def skip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the recipe selection."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Geen probleem! Laat het me weten als je receptideeën wilt.")
    return ConversationHandler.END


async def ingredient_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the choice between adding all ingredients or selecting a subset."""
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        await query.edit_message_text("Geannuleerd. Laat het me weten als je receptideeën wilt!")
        return ConversationHandler.END

    all_ingredients: list[str] = context.user_data.get("all_ingredients", [])

    if query.data == "confirm_all":
        await query.edit_message_text("⏳ Even geduld, ik voeg de ingrediënten toe...")
        result = add_ingredients_to_cart(all_ingredients)
        reply = _format_cart_result(context.user_data.get("selected_recipes", []), result)
        await query.edit_message_text(reply, parse_mode="HTML", disable_web_page_preview=True)
        return ConversationHandler.END

    # confirm_choose: show ingredient selection keyboard
    selected_indices = set(range(len(all_ingredients)))  # all pre-selected
    context.user_data["selected_ingredient_indices"] = selected_indices
    keyboard = _build_ingredient_keyboard(all_ingredients, selected_indices)

    await query.edit_message_text(
        "Selecteer de ingrediënten die je wilt toevoegen:",
        reply_markup=keyboard,
    )
    return SELECTING_INGREDIENTS


async def toggle_ingredient_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle an individual ingredient's selection state."""
    query = update.callback_query
    await query.answer()

    index = int(query.data.split("_")[2])  # ing_toggle_X
    selected: set = context.user_data.get("selected_ingredient_indices", set())

    if index in selected:
        selected.discard(index)
    else:
        selected.add(index)
    context.user_data["selected_ingredient_indices"] = selected

    all_ingredients = context.user_data.get("all_ingredients", [])
    await query.edit_message_reply_markup(
        reply_markup=_build_ingredient_keyboard(all_ingredients, selected)
    )
    return SELECTING_INGREDIENTS


async def confirm_ingredients_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Add the selected ingredients to the Picnic cart."""
    query = update.callback_query

    if query.data == "ing_cancel":
        await query.answer()
        await query.edit_message_text("Geannuleerd. Laat het me weten als je receptideeën wilt!")
        return ConversationHandler.END

    selected_indices: set = context.user_data.get("selected_ingredient_indices", set())
    if not selected_indices:
        await query.answer("Selecteer minimaal één ingrediënt.", show_alert=True)
        return SELECTING_INGREDIENTS

    await query.answer()
    all_ingredients = context.user_data.get("all_ingredients", [])
    chosen_ingredients = [all_ingredients[i] for i in sorted(selected_indices)]

    await query.message.chat.send_action(action="typing")
    result = add_ingredients_to_cart(chosen_ingredients)
    reply = _format_cart_result(
        context.user_data.get("selected_recipes", []), result, chosen_ingredients
    )
    await query.edit_message_text(reply, parse_mode="HTML", disable_web_page_preview=True)
    return ConversationHandler.END


def main():
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("help", help_command))

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_ingredients),
        ],
        states={
            ASKING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            CHOOSING: [
                CallbackQueryHandler(toggle_handler,       pattern=r"^toggle_\d+$"),
                CallbackQueryHandler(add_selected_handler, pattern=r"^add_selected$"),
                CallbackQueryHandler(skip_handler,         pattern=r"^recipe_no$"),
            ],
            CONFIRMING: [
                CallbackQueryHandler(ingredient_choice_handler, pattern=r"^confirm_"),
            ],
            SELECTING_INGREDIENTS: [
                CallbackQueryHandler(toggle_ingredient_handler,   pattern=r"^ing_toggle_\d+$"),
                CallbackQueryHandler(confirm_ingredients_handler, pattern=r"^ing_(confirm|cancel)$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    application.add_handler(conv_handler)

    async def stale_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.callback_query.answer(
            "Deze sessie is verlopen. Stuur me je ingrediënten om opnieuw te beginnen.",
            show_alert=True,
        )

    application.add_handler(CallbackQueryHandler(stale_callback_handler))

    if ENVIRONMENT == 'production':
        if not WEBHOOK_URL:
            raise RuntimeError("WEBHOOK_URL must be set in production mode")
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
