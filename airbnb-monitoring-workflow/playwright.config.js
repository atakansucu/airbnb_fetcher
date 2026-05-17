module.exports = {
  timeout: 30000,
  use: {
    headless: true,
    ignoreDefaultArgs: ['--disable-extensions'],
    launchOptions: {
      slowMo: 50,
    },
  },
  projects: [
    {
      name: 'Chromium',
      use: { browserName: 'chromium' },
    },
    {
      name: 'Firefox',
      use: { browserName: 'firefox' },
    },
    {
      name: 'WebKit',
      use: { browserName: 'webkit' },
    },
  ],
};