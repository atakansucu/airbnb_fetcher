module.exports = {
    info: (message) => {
        console.log(`[INFO] ${new Date().toISOString()}: ${message}`);
    },
    warning: (message) => {
        console.warn(`[WARNING] ${new Date().toISOString()}: ${message}`);
    },
    error: (message) => {
        console.error(`[ERROR] ${new Date().toISOString()}: ${message}`);
    },
    logEvent: (eventType, details) => {
        console.log(`[EVENT] ${new Date().toISOString()}: ${eventType} - ${details}`);
    }
};