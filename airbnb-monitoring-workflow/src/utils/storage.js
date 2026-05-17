exports.readSeenListings = function(filePath) {
    const fs = require('fs');

    if (!fs.existsSync(filePath)) {
        return [];
    }

    const data = fs.readFileSync(filePath, 'utf8');
    return JSON.parse(data);
};

exports.writeSeenListings = function(filePath, listings) {
    const fs = require('fs');
    fs.writeFileSync(filePath, JSON.stringify(listings, null, 2));
};