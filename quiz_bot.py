import logging
import asyncio
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
import google.generativeai as genai

# लॉगिंग सेट करें
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# पर्यावरण वैरिएबल से एपीआई टोकन और कुंजी लें
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
    logging.error("TELEGRAM_BOT_TOKEN या GEMINI_API_KEY सेट नहीं है।")
    exit()

# Gemini API को कॉन्फ़िगर करें
genai.configure(api_key=GEMINI_API_KEY)

# Gemini मॉडल लोड करें
model = genai.GenerativeModel("gemini-1.5-flash")

# क्विज़ के विषय
QUIZ_TOPICS = ["इतिहास", "विज्ञान", "भूगोल", "कला", "खेल", "प्रौद्योगिकी"]

# उपयोगकर्ता के लिए क्विज़ की स्थिति को स्टोर करने के लिए डिक्शनरी
user_data = {}
MAX_QUIZZES = 100

# /start कमांड के लिए फ़ंक्शन
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """जब उपयोगकर्ता /start कमांड जारी करता है तो यह संदेश भेजता है और बटन दिखाता है."""
    user_data[update.effective_user.id] = {"quiz_count": 0, "current_topic": None}
    
    keyboard = [
        [InlineKeyboardButton(topic, callback_data=f"topic_{topic}")]
        for topic in QUIZ_TOPICS
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(
        "नमस्ते! मैं एक AI-संचालित क्विज़ बॉट हूँ. आप किस विषय पर क्विज़ खेलना चाहेंगे?",
        reply_markup=reply_markup,
    )

# क्विज़ जनरेट करने का फ़ंक्शन
async def generate_quiz(topic: str) -> dict:
    """Gemini API का उपयोग करके हिंदी में क्विज़ जनरेट करें."""
    prompt = f"""
    एक क्विज़ के लिए एक JSON ऑब्जेक्ट जनरेट करें जिसमें एक सवाल, चार विकल्प (A, B, C, D), सही उत्तर का अक्षर (A, B, C या D) और सही उत्तर की एक संक्षिप्त व्याख्या हो.
    यह क्विज़ "{topic}" विषय पर होनी चाहिए.
    उदाहरण:
    {{
      "question": "मानव शरीर की सबसे बड़ी हड्डी कौन सी है?",
      "options": {{
        "A": "फ़ेमर",
        "B": "टिबिआ",
        "C": "फ़िबुला",
        "D": "ह्यूमरस"
      }},
      "correct_answer": "A",
      "explanation": "फ़ेमर, जिसे जाँघ की हड्डी भी कहते हैं, मानव शरीर की सबसे लंबी और सबसे मजबूत हड्डी है."
    }}
    JSON में सिर्फ़ यही एक ऑब्जेक्ट होना चाहिए.
    """
    try:
        response = model.generate_content(prompt)
        quiz_data_str = response.text.replace("```json", "").replace("```", "").strip()
        quiz_data = json.loads(quiz_data_str)
        return quiz_data
    except Exception as e:
        logging.error(f"Failed to generate quiz: {e}")
        return None

# क्विज़ भेजने का फ़ंक्शन
async def send_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """उपयोगकर्ता को नया क्विज़ भेजें."""
    user_id = update.effective_user.id
    if user_id not in user_data or not user_data[user_id].get("current_topic"):
        await update.message.reply_text("कृपया पहले /start कमांड से एक विषय चुनें.")
        return

    current_topic = user_data[user_id]["current_topic"]
    
    # क्विज़ की गिनती जाँचें
    if user_data[user_id]["quiz_count"] >= MAX_QUIZZES:
        await update.message.reply_text(
            "आप 100 क्विज़ पूरे कर चुके हैं. नया क्विज़ शुरू करने के लिए /start कमांड का उपयोग करें."
        )
        return

    quiz = await generate_quiz(current_topic)
    if not quiz:
        await update.message.reply_text("माफ़ कीजिए, क्विज़ जनरेट करने में कोई समस्या हुई.")
        return

    user_data[user_id]["quiz"] = quiz
    user_data[user_id]["quiz_count"] += 1

    question = quiz["question"]
    options = quiz["options"]
    message_text = f"<b>सवाल:</b> {question}\n\n"
    for key, value in options.items():
        message_text += f"<b>{key}:</b> {value}\n"
    
    # स्टॉप बटन जोड़ें
    stop_keyboard = [
        [InlineKeyboardButton("बंद करें", callback_data="stop_quiz")]
    ]
    stop_reply_markup = InlineKeyboardMarkup(stop_keyboard)
    
    await update.message.reply_html(message_text, reply_markup=stop_reply_markup)

# बटन (callback query) को हैंडल करने का फ़ंक्शन
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """बटन पर क्लिक होने पर जवाब दें."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_data:
        await start(query, context)
        return
        
    data = query.data

    if data.startswith("topic_"):
        topic = data.split("_")[1]
        user_data[user_id]["current_topic"] = topic
        user_data[user_id]["quiz_count"] = 0
        await query.edit_message_text(f"ठीक है, हम {topic} पर क्विज़ शुरू कर रहे हैं...")
        await send_quiz(query, context)
    elif data == "stop_quiz":
        user_data[user_id]["current_topic"] = None
        user_data[user_id]["quiz_count"] = 0
        await query.edit_message_text("क्विज़ बंद कर दिया गया है. नया क्विज़ शुरू करने के लिए /start कमांड का उपयोग करें.")
        

# उपयोगकर्ता के जवाब को हैंडल करने का फ़ंक्शन
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """उपयोगकर्ता के उत्तर की जाँच करें और अगला क्विज़ शेड्यूल करें."""
    user_id = update.effective_user.id
    if user_id not in user_data or not user_data[user_id].get("current_topic"):
        await update.message.reply_text("कृपया पहले /start कमांड से एक विषय चुनें.")
        return

    user_answer = update.message.text.strip().upper()
    quiz = user_data[user_id]["quiz"]
    correct_answer = quiz["correct_answer"].upper()

    if user_answer == correct_answer:
        explanation = quiz["explanation"]
        await update.message.reply_text(f"सही जवाब! 🎉\n\n<b>व्याख्या:</b> {explanation}", parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"ग़लत जवाब! 😔\nसही जवाब था: <b>{correct_answer}</b>\n\n<b>व्याख्या:</b> {quiz['explanation']}",
            parse_mode="HTML",
        )

    # 15 सेकंड के बाद अगला क्विज़ भेजें
    await asyncio.sleep(15)
    await send_quiz(update, context)


# मुख्य फ़ंक्शन जो बॉट को चलाएगा
def main() -> None:
    """बॉट चलाएँ."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))
    
    # बॉट को शुरू करें
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
