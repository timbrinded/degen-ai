import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(defineConfig({
  title: 'Hyperliquid Trading Agent',
  description: 'AI-powered trading agent for Hyperliquid perpetual futures',
  base: '/degen-ai/',
  ignoreDeadLinks: true,
  
  themeConfig: {
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'Architecture', link: '/architecture/overview' },
      { text: 'Strategies', link: '/strategies/' },
      { text: 'API', link: '/api/' }
    ],

    sidebar: [
      {
        text: 'Guide',
        items: [
          { text: 'Introduction', link: '/guide/introduction' },
          { text: 'Getting Started', link: '/guide/getting-started' },
          { text: 'CLI Reference', link: '/guide/cli-reference' },
          { text: 'Configuration', link: '/guide/configuration' },
          { text: 'Backtesting', link: '/guide/backtesting' },
          { text: 'Deployment', link: '/guide/deployment' },
          { text: 'Troubleshooting', link: '/guide/troubleshooting' }
        ]
      },
      {
        text: 'Architecture',
        items: [
          { text: 'Overview', link: '/architecture/overview' },
          { text: 'Governance', link: '/architecture/governance' },
          { text: 'Signals', link: '/architecture/signals' },
          { text: 'Portfolio Management', link: '/architecture/portfolio' },
          { text: 'Monitoring', link: '/architecture/monitoring' },
          { text: 'Decision Engine', link: '/architecture/decision-engine' },
          { text: 'Market Registry', link: '/architecture/market-registry' },
          { text: 'Performance', link: '/architecture/performance' }
        ]
      },
      {
        text: 'Strategies',
        items: [
          { text: 'Overview', link: '/strategies/' },
          { text: 'Funding Harvest', link: '/strategies/funding-harvest' },
          { text: 'Trend Following', link: '/strategies/trend-following' },
          { text: 'Funding Flip Fade', link: '/strategies/funding-flip-fade' },
          { text: 'Slowrider Trend', link: '/strategies/slowrider-trend' },
          { text: 'Compression Pop', link: '/strategies/compression-pop' },
          { text: 'Range Sip', link: '/strategies/range-sip' },
          { text: 'OI Drift Divergence', link: '/strategies/oi-drift-divergence' },
          { text: 'Session Bias', link: '/strategies/session-bias' },
          { text: 'Funding Calendar Clip', link: '/strategies/funding-calendar-clip' },
          { text: 'Markfix Mean Revert', link: '/strategies/markfix-mean-revert' },
          { text: 'Pairs Beta Sync', link: '/strategies/pairs-beta-sync' },
          { text: 'Unlock Watch', link: '/strategies/unlock-watch' }
        ]
      },
      {
        text: 'API Reference',
        items: [
          { text: 'Overview', link: '/api/' },
          { text: 'Core', link: '/api/core' },
          { text: 'Governance', link: '/api/governance' },
          { text: 'Signals', link: '/api/signals' },
          { text: 'Backtesting', link: '/api/backtesting' }
        ]
      }
    ],

    search: {
      provider: 'local',
      options: {
        detailedView: true
      }
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/yourusername/hyperliquid-trading-agent' }
    ]
  }
}))
