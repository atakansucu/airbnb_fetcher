const axios = require('axios');

const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID;

const sendTelegramMessage = async (message) => {
    try {
        await axios.post(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`, {
            chat_id: TELEGRAM_CHAT_ID,
            text: message,
            parse_mode: 'Markdown',
        });
        console.log('Notification sent:', message);
    } catch (error) {
        console.error('Error sending notification:', error);
    }
};

const notifyNewListing = (listing) => {
    const message = `New listing found: *${listing.title}*\nPrice: *${listing.price}*\nLink: ${listing.url}`;
    sendTelegramMessage(message);
};

const notifyPriceDrop = (listing) => {
    const message = `Price drop alert for: *${listing.title}*\nNew Price: *${listing.price}*\nLink: ${listing.url}`;
    sendTelegramMessage(message);
};

const notifyRareDeal = (listing) => {
    const message = `Rare deal alert for: *${listing.title}*\nPrice: *${listing.price}*\nLink: ${listing.url}`;
    sendTelegramMessage(message);
};

module.exports = {
    notifyNewListing,
    notifyPriceDrop,
    notifyRareDeal,
};