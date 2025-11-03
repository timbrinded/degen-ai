import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Hyperliquid Trading Agent',
  description: 'AI-powered trading agent for Hyperliquid perpetual futures',
  base: '/hyperliquid-trading-agent/',
  
  themeConfig: {
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'Strategies', link: '/strategies/' }
    ],

    sidebar: [
      {
        text: 'Introduction',
        items: [
          { text: 'What is it?', link: '/guide/introduction' },
          { text: 'Getting Started', link: '/guide/getting-started' },
          { text: 'Configuration', link: '/guide/configuration' }
        ]
      },
      {
        text: 'Architecture',
        items: [
          { text: 'Overview', link: '/architecture/overview' },
          { text: 'Signal System', link: '/architecture/signals' },
          { text: 'Governance', link: '/architecture/governance' }
        ]
      },
      {
        text: 'Strategies',
        items: [
          { text: 'Overview', link: '/strategies/' },
          { text: 'Funding Harvest', link: '/strategies/funding-harvest' },
          { text: 'Trend Following', link: '/strategies/trend-following' }
        ]
      }
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/yourusername/hyperliquid-trading-agent' }
    ]
  }
})
