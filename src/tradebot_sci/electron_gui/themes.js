/**
 * Tradebot SCI — Theme Engine
 * Manages 30 UI themes with CSS variable overrides and optional background images.
 * Persists selection to localStorage. Auto-applies saved theme on load.
 */

const THEMES = {
    // ── COLOR-ONLY THEMES ────────────────────────────────────────
    obsidian: {
        name: 'Obsidian',
        description: 'Default dark theme',
        category: 'color',
        preview: ['#020617', '#14b8a6', '#0d9488', '#115e59'],
        vars: {
            '--bg-dark': '#020617',
            '--bg-card': 'rgba(15, 23, 42, 0.4)',
            '--bg-card-hover': 'rgba(30, 41, 59, 0.5)',
            '--card-border': 'rgba(255, 255, 255, 0.06)',
            '--card-border-hover': 'rgba(20, 184, 166, 0.4)',
            '--accent': '#14b8a6',
            '--accent-dim': 'rgba(20, 184, 166, 0.15)',
            '--accent-glow': 'rgba(20, 184, 166, 0.25)',
            '--accent-hover': '#0d9488',
            '--purple': '#8b5cf6',
            '--purple-dim': 'rgba(139, 92, 246, 0.15)',
            '--text-main': '#f1f5f9',
            '--text-secondary': '#94a3b8',
            '--text-muted': '#64748b',
            '--text-dim': '#475569',
            '--success': '#10b981',
            '--warning': '#f59e0b',
            '--error': '#ef4444',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #115e59 0%, #020617 90%)',
        titlebar: 'linear-gradient(90deg, #0058e6 0%, #002159 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #0d9488 0%, #1e1b4b 60%, transparent 100%)',
        meshOpacity: 0.5,
        candleUp: '#2dd4bf',
        candleDown: '#f43f5e',
    },

    midnight: {
        name: 'Midnight Blue',
        description: 'Deep navy with electric blue',
        category: 'color',
        preview: ['#0a0e27', '#3b82f6', '#1d4ed8', '#1e3a5f'],
        vars: {
            '--bg-dark': '#0a0e27',
            '--bg-card': 'rgba(10, 14, 39, 0.5)',
            '--bg-card-hover': 'rgba(29, 38, 68, 0.5)',
            '--card-border': 'rgba(59, 130, 246, 0.1)',
            '--card-border-hover': 'rgba(59, 130, 246, 0.4)',
            '--accent': '#3b82f6',
            '--accent-dim': 'rgba(59, 130, 246, 0.15)',
            '--accent-glow': 'rgba(59, 130, 246, 0.25)',
            '--accent-hover': '#2563eb',
            '--purple': '#a78bfa',
            '--purple-dim': 'rgba(167, 139, 250, 0.15)',
            '--text-main': '#e2e8f0',
            '--text-secondary': '#94a3b8',
            '--text-muted': '#64748b',
            '--text-dim': '#475569',
            '--success': '#22d3ee',
            '--warning': '#fbbf24',
            '--error': '#f87171',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #1e3a5f 0%, #0a0e27 90%)',
        titlebar: 'linear-gradient(90deg, #1d4ed8 0%, #0a0e27 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #1d4ed8 0%, #312e81 60%, transparent 100%)',
        meshOpacity: 0.4,
        candleUp: '#3b82f6',
        candleDown: '#f87171',
    },

    matrix: {
        name: 'Neon Matrix',
        description: 'Hacker green terminal',
        category: 'color',
        preview: ['#000000', '#00ff41', '#008f11', '#003300'],
        vars: {
            '--bg-dark': '#000000',
            '--bg-card': 'rgba(0, 15, 0, 0.5)',
            '--bg-card-hover': 'rgba(0, 30, 0, 0.5)',
            '--card-border': 'rgba(0, 255, 65, 0.08)',
            '--card-border-hover': 'rgba(0, 255, 65, 0.3)',
            '--accent': '#00ff41',
            '--accent-dim': 'rgba(0, 255, 65, 0.12)',
            '--accent-glow': 'rgba(0, 255, 65, 0.2)',
            '--accent-hover': '#00cc33',
            '--purple': '#00ff41',
            '--purple-dim': 'rgba(0, 255, 65, 0.1)',
            '--text-main': '#00ff41',
            '--text-secondary': '#00cc33',
            '--text-muted': '#008f11',
            '--text-dim': '#005500',
            '--success': '#00ff41',
            '--warning': '#ffff00',
            '--error': '#ff0000',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #003300 0%, #000000 90%)',
        titlebar: 'linear-gradient(90deg, #003300 0%, #000000 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #008f11 0%, #001100 60%, transparent 100%)',
        meshOpacity: 0.3,
        candleUp: '#00ff41',
        candleDown: '#ff0000',
    },

    arctic: {
        name: 'Arctic Frost',
        description: 'Icy whites and cool blues',
        category: 'color',
        preview: ['#0c1929', '#7dd3fc', '#0ea5e9', '#164e63'],
        vars: {
            '--bg-dark': '#0c1929',
            '--bg-card': 'rgba(12, 25, 41, 0.5)',
            '--bg-card-hover': 'rgba(22, 78, 99, 0.3)',
            '--card-border': 'rgba(125, 211, 252, 0.1)',
            '--card-border-hover': 'rgba(125, 211, 252, 0.4)',
            '--accent': '#7dd3fc',
            '--accent-dim': 'rgba(125, 211, 252, 0.15)',
            '--accent-glow': 'rgba(125, 211, 252, 0.25)',
            '--accent-hover': '#38bdf8',
            '--purple': '#c4b5fd',
            '--purple-dim': 'rgba(196, 181, 253, 0.15)',
            '--text-main': '#e0f2fe',
            '--text-secondary': '#bae6fd',
            '--text-muted': '#7dd3fc',
            '--text-dim': '#0369a1',
            '--success': '#67e8f9',
            '--warning': '#fde68a',
            '--error': '#fca5a5',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #164e63 0%, #0c1929 90%)',
        titlebar: 'linear-gradient(90deg, #0369a1 0%, #0c1929 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #0ea5e9 0%, #1e1b4b 60%, transparent 100%)',
        meshOpacity: 0.35,
        candleUp: '#7dd3fc',
        candleDown: '#fca5a5',
    },

    sunset: {
        name: 'Sunset Trading',
        description: 'Warm orange and deep reds',
        category: 'color',
        preview: ['#1a0a00', '#f97316', '#dc2626', '#7c2d12'],
        vars: {
            '--bg-dark': '#1a0a00',
            '--bg-card': 'rgba(26, 10, 0, 0.5)',
            '--bg-card-hover': 'rgba(60, 20, 0, 0.5)',
            '--card-border': 'rgba(249, 115, 22, 0.1)',
            '--card-border-hover': 'rgba(249, 115, 22, 0.4)',
            '--accent': '#f97316',
            '--accent-dim': 'rgba(249, 115, 22, 0.15)',
            '--accent-glow': 'rgba(249, 115, 22, 0.25)',
            '--accent-hover': '#ea580c',
            '--purple': '#fb923c',
            '--purple-dim': 'rgba(251, 146, 60, 0.15)',
            '--text-main': '#fef3c7',
            '--text-secondary': '#fed7aa',
            '--text-muted': '#c2410c',
            '--text-dim': '#7c2d12',
            '--success': '#34d399',
            '--warning': '#fbbf24',
            '--error': '#dc2626',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #7c2d12 0%, #1a0a00 90%)',
        titlebar: 'linear-gradient(90deg, #dc2626 0%, #7c2d12 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #f97316 0%, #7c2d12 60%, transparent 100%)',
        meshOpacity: 0.35,
        candleUp: '#f97316',
        candleDown: '#dc2626',
    },

    ocean: {
        name: 'Ocean Depth',
        description: 'Deep sea teal and navy',
        category: 'color',
        preview: ['#001219', '#0a9396', '#005f73', '#002b36'],
        vars: {
            '--bg-dark': '#001219',
            '--bg-card': 'rgba(0, 18, 25, 0.5)',
            '--bg-card-hover': 'rgba(0, 43, 54, 0.5)',
            '--card-border': 'rgba(10, 147, 150, 0.12)',
            '--card-border-hover': 'rgba(10, 147, 150, 0.4)',
            '--accent': '#0a9396',
            '--accent-dim': 'rgba(10, 147, 150, 0.15)',
            '--accent-glow': 'rgba(10, 147, 150, 0.25)',
            '--accent-hover': '#008f8c',
            '--purple': '#94d2bd',
            '--purple-dim': 'rgba(148, 210, 189, 0.15)',
            '--text-main': '#e9d8a6',
            '--text-secondary': '#94d2bd',
            '--text-muted': '#0a9396',
            '--text-dim': '#005f73',
            '--success': '#40c9a2',
            '--warning': '#ee9b00',
            '--error': '#ae2012',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #002b36 0%, #001219 90%)',
        titlebar: 'linear-gradient(90deg, #005f73 0%, #001219 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #0a9396 0%, #001219 60%, transparent 100%)',
        meshOpacity: 0.4,
        candleUp: '#0a9396',
        candleDown: '#ae2012',
    },

    gold: {
        name: 'Gold Standard',
        description: 'Black and gold luxury',
        category: 'color',
        preview: ['#0a0a0a', '#d4a017', '#b8860b', '#2d1f00'],
        vars: {
            '--bg-dark': '#0a0a0a',
            '--bg-card': 'rgba(10, 10, 10, 0.6)',
            '--bg-card-hover': 'rgba(30, 20, 0, 0.5)',
            '--card-border': 'rgba(212, 160, 23, 0.1)',
            '--card-border-hover': 'rgba(212, 160, 23, 0.4)',
            '--accent': '#d4a017',
            '--accent-dim': 'rgba(212, 160, 23, 0.15)',
            '--accent-glow': 'rgba(212, 160, 23, 0.25)',
            '--accent-hover': '#b8860b',
            '--purple': '#e8c547',
            '--purple-dim': 'rgba(232, 197, 71, 0.15)',
            '--text-main': '#f5e6c8',
            '--text-secondary': '#d4a017',
            '--text-muted': '#8b6914',
            '--text-dim': '#4a3800',
            '--success': '#22c55e',
            '--warning': '#d4a017',
            '--error': '#dc2626',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #2d1f00 0%, #0a0a0a 90%)',
        titlebar: 'linear-gradient(90deg, #b8860b 0%, #2d1f00 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #b8860b 0%, #1a1000 60%, transparent 100%)',
        meshOpacity: 0.3,
        candleUp: '#d4a017',
        candleDown: '#dc2626',
    },

    sakura: {
        name: 'Sakura',
        description: 'Soft pinks and purple',
        category: 'color',
        preview: ['#1a0a1a', '#f472b6', '#a855f7', '#4a1942'],
        vars: {
            '--bg-dark': '#1a0a1a',
            '--bg-card': 'rgba(26, 10, 26, 0.5)',
            '--bg-card-hover': 'rgba(50, 20, 50, 0.5)',
            '--card-border': 'rgba(244, 114, 182, 0.1)',
            '--card-border-hover': 'rgba(244, 114, 182, 0.4)',
            '--accent': '#f472b6',
            '--accent-dim': 'rgba(244, 114, 182, 0.15)',
            '--accent-glow': 'rgba(244, 114, 182, 0.25)',
            '--accent-hover': '#ec4899',
            '--purple': '#c084fc',
            '--purple-dim': 'rgba(192, 132, 252, 0.15)',
            '--text-main': '#fce7f3',
            '--text-secondary': '#f9a8d4',
            '--text-muted': '#be185d',
            '--text-dim': '#831843',
            '--success': '#34d399',
            '--warning': '#fbbf24',
            '--error': '#f43f5e',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #4a1942 0%, #1a0a1a 90%)',
        titlebar: 'linear-gradient(90deg, #a855f7 0%, #4a1942 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #ec4899 0%, #4c1d95 60%, transparent 100%)',
        meshOpacity: 0.35,
        candleUp: '#f472b6',
        candleDown: '#f43f5e',
    },

    stealth: {
        name: 'Stealth',
        description: 'Pure black OLED minimal',
        category: 'color',
        preview: ['#000000', '#525252', '#404040', '#171717'],
        vars: {
            '--bg-dark': '#000000',
            '--bg-card': 'rgba(0, 0, 0, 0.6)',
            '--bg-card-hover': 'rgba(23, 23, 23, 0.5)',
            '--card-border': 'rgba(82, 82, 82, 0.15)',
            '--card-border-hover': 'rgba(82, 82, 82, 0.4)',
            '--accent': '#a3a3a3',
            '--accent-dim': 'rgba(163, 163, 163, 0.1)',
            '--accent-glow': 'rgba(163, 163, 163, 0.15)',
            '--accent-hover': '#737373',
            '--purple': '#a3a3a3',
            '--purple-dim': 'rgba(163, 163, 163, 0.1)',
            '--text-main': '#d4d4d4',
            '--text-secondary': '#a3a3a3',
            '--text-muted': '#525252',
            '--text-dim': '#404040',
            '--success': '#4ade80',
            '--warning': '#fbbf24',
            '--error': '#f87171',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #171717 0%, #000000 90%)',
        titlebar: 'linear-gradient(90deg, #262626 0%, #000000 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #262626 0%, #000000 60%, transparent 100%)',
        meshOpacity: 0.2,
        candleUp: '#a3a3a3',
        candleDown: '#f87171',
    },

    light: {
        name: 'Light Mode',
        description: 'Clean whites and blue',
        category: 'color',
        preview: ['#f1f5f9', '#0369a1', '#0284c7', '#e2e8f0'],
        vars: {
            '--bg-dark': '#f1f5f9',
            '--bg-card': 'rgba(255, 255, 255, 0.7)',
            '--bg-card-hover': 'rgba(255, 255, 255, 0.9)',
            '--card-border': 'rgba(0, 0, 0, 0.08)',
            '--card-border-hover': 'rgba(3, 105, 161, 0.4)',
            '--accent': '#0369a1',
            '--accent-dim': 'rgba(3, 105, 161, 0.1)',
            '--accent-glow': 'rgba(3, 105, 161, 0.15)',
            '--accent-hover': '#0284c7',
            '--purple': '#7c3aed',
            '--purple-dim': 'rgba(124, 58, 237, 0.1)',
            '--text-main': '#0f172a',
            '--text-secondary': '#334155',
            '--text-muted': '#64748b',
            '--text-dim': '#94a3b8',
            '--success': '#059669',
            '--warning': '#d97706',
            '--error': '#dc2626',
        },
        sidebar: 'linear-gradient(180deg, #e2e8f0 0%, #f1f5f9 100%)',
        titlebar: 'linear-gradient(90deg, #0369a1 0%, #0284c7 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #bae6fd 0%, #f1f5f9 60%, transparent 100%)',
        meshOpacity: 0.6,
        candleUp: '#0369a1',
        candleDown: '#dc2626',
    },

    // ── IMAGE THEMES ────────────────────────────────────────────
    anime: {
        name: 'Hacker',
        description: 'Anime · Dark violet cyber aesthetic',
        category: 'image',
        preview: ['#1a0a2e', '#c084fc', '#7c3aed', '#2e1065'],
        backgroundImage: './assets/themes/anime_theme.png',
        vars: {
            '--bg-dark': '#1a0a2e',
            '--bg-card': 'rgba(15, 5, 30, 0.7)',
            '--bg-card-hover': 'rgba(30, 10, 50, 0.7)',
            '--card-border': 'rgba(192, 132, 252, 0.12)',
            '--card-border-hover': 'rgba(192, 132, 252, 0.4)',
            '--accent': '#c084fc',
            '--accent-dim': 'rgba(192, 132, 252, 0.15)',
            '--accent-glow': 'rgba(192, 132, 252, 0.25)',
            '--accent-hover': '#a855f7',
            '--purple': '#e879f9',
            '--purple-dim': 'rgba(232, 121, 249, 0.15)',
            '--text-main': '#f5f3ff',
            '--text-secondary': '#c4b5fd',
            '--text-muted': '#7c3aed',
            '--text-dim': '#4c1d95',
            '--success': '#34d399',
            '--warning': '#fbbf24',
            '--error': '#f43f5e',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #2e1065 0%, rgba(10,5,20,0.95) 90%)',
        titlebar: 'linear-gradient(90deg, #7c3aed 0%, #2e1065 100%)',
        meshGradient: 'none',
        meshOpacity: 0,
        candleUp: '#c084fc',
        candleDown: '#f43f5e',
    },

    cyberpunk: {
        name: 'Cyberpunk',
        description: 'Neon-lit dystopia',
        category: 'image',
        preview: ['#0a001a', '#ff006e', '#00f5d4', '#240046'],
        backgroundImage: './assets/themes/cyberpunk_theme.png',
        vars: {
            '--bg-dark': '#0a001a',
            '--bg-card': 'rgba(10, 0, 26, 0.75)',
            '--bg-card-hover': 'rgba(20, 0, 40, 0.75)',
            '--card-border': 'rgba(255, 0, 110, 0.12)',
            '--card-border-hover': 'rgba(255, 0, 110, 0.4)',
            '--accent': '#ff006e',
            '--accent-dim': 'rgba(255, 0, 110, 0.15)',
            '--accent-glow': 'rgba(255, 0, 110, 0.25)',
            '--accent-hover': '#d6336c',
            '--purple': '#00f5d4',
            '--purple-dim': 'rgba(0, 245, 212, 0.15)',
            '--text-main': '#f8f9fa',
            '--text-secondary': '#dee2e6',
            '--text-muted': '#868e96',
            '--text-dim': '#495057',
            '--success': '#00f5d4',
            '--warning': '#ffe066',
            '--error': '#ff006e',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #240046 0%, rgba(5,0,15,0.95) 90%)',
        titlebar: 'linear-gradient(90deg, #ff006e 0%, #240046 100%)',
        meshGradient: 'none',
        meshOpacity: 0,
        candleUp: '#00f5d4',
        candleDown: '#ff006e',
    },

    nature: {
        name: 'Nature',
        description: 'Foggy forest serenity',
        category: 'image',
        preview: ['#0a1a0a', '#22c55e', '#15803d', '#14532d'],
        backgroundImage: './assets/themes/nature_theme.png',
        vars: {
            '--bg-dark': '#0a1a0a',
            '--bg-card': 'rgba(10, 20, 10, 0.75)',
            '--bg-card-hover': 'rgba(20, 40, 20, 0.75)',
            '--card-border': 'rgba(34, 197, 94, 0.12)',
            '--card-border-hover': 'rgba(34, 197, 94, 0.4)',
            '--accent': '#22c55e',
            '--accent-dim': 'rgba(34, 197, 94, 0.15)',
            '--accent-glow': 'rgba(34, 197, 94, 0.25)',
            '--accent-hover': '#16a34a',
            '--purple': '#86efac',
            '--purple-dim': 'rgba(134, 239, 172, 0.15)',
            '--text-main': '#ecfdf5',
            '--text-secondary': '#a7f3d0',
            '--text-muted': '#22c55e',
            '--text-dim': '#14532d',
            '--success': '#34d399',
            '--warning': '#fbbf24',
            '--error': '#f87171',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #14532d 0%, rgba(5,12,5,0.95) 90%)',
        titlebar: 'linear-gradient(90deg, #15803d 0%, #052e16 100%)',
        meshGradient: 'none',
        meshOpacity: 0,
        candleUp: '#22c55e',
        candleDown: '#f87171',
    },

    city: {
        name: 'Neon City',
        description: 'Chinese megacity at night',
        category: 'image',
        preview: ['#0d0805', '#f59e0b', '#ef4444', '#451a03'],
        backgroundImage: './assets/themes/city_theme.png',
        vars: {
            '--bg-dark': '#0d0805',
            '--bg-card': 'rgba(13, 8, 5, 0.75)',
            '--bg-card-hover': 'rgba(30, 15, 5, 0.75)',
            '--card-border': 'rgba(245, 158, 11, 0.12)',
            '--card-border-hover': 'rgba(245, 158, 11, 0.4)',
            '--accent': '#f59e0b',
            '--accent-dim': 'rgba(245, 158, 11, 0.15)',
            '--accent-glow': 'rgba(245, 158, 11, 0.25)',
            '--accent-hover': '#d97706',
            '--purple': '#fbbf24',
            '--purple-dim': 'rgba(251, 191, 36, 0.15)',
            '--text-main': '#fef3c7',
            '--text-secondary': '#fde68a',
            '--text-muted': '#b45309',
            '--text-dim': '#78350f',
            '--success': '#34d399',
            '--warning': '#f59e0b',
            '--error': '#ef4444',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #451a03 0%, rgba(8,4,2,0.95) 90%)',
        titlebar: 'linear-gradient(90deg, #b45309 0%, #451a03 100%)',
        meshGradient: 'none',
        meshOpacity: 0,
        candleUp: '#f59e0b',
        candleDown: '#ef4444',
    },

    cosmos: {
        name: 'Cosmos',
        description: 'Deep space nebula',
        category: 'image',
        preview: ['#05000d', '#8b5cf6', '#6d28d9', '#1e1b4b'],
        backgroundImage: './assets/themes/cosmos_theme.png',
        vars: {
            '--bg-dark': '#05000d',
            '--bg-card': 'rgba(5, 0, 13, 0.75)',
            '--bg-card-hover': 'rgba(15, 5, 30, 0.75)',
            '--card-border': 'rgba(139, 92, 246, 0.12)',
            '--card-border-hover': 'rgba(139, 92, 246, 0.4)',
            '--accent': '#a78bfa',
            '--accent-dim': 'rgba(167, 139, 250, 0.15)',
            '--accent-glow': 'rgba(167, 139, 250, 0.25)',
            '--accent-hover': '#8b5cf6',
            '--purple': '#c4b5fd',
            '--purple-dim': 'rgba(196, 181, 253, 0.15)',
            '--text-main': '#ede9fe',
            '--text-secondary': '#c4b5fd',
            '--text-muted': '#7c3aed',
            '--text-dim': '#4c1d95',
            '--success': '#34d399',
            '--warning': '#fbbf24',
            '--error': '#f43f5e',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #1e1b4b 0%, rgba(3,0,8,0.95) 90%)',
        titlebar: 'linear-gradient(90deg, #6d28d9 0%, #1e1b4b 100%)',
        meshGradient: 'none',
        meshOpacity: 0,
        candleUp: '#a78bfa',
        candleDown: '#f43f5e',
    },

    // ── NEW THEMES ──────────────────────────────────────────────

    // ANIME
    kawaii: {
        name: 'Magical Girl',
        description: 'Anime · Kawaii pastel dream',
        category: 'image',
        preview: ['#1a0d1e', '#f9a8d4', '#e879f9', '#4a1942'],
        backgroundImage: './assets/themes/kawaii_theme.png',
        vars: {
            '--bg-dark': '#1a0d1e',
            '--bg-card': 'rgba(26, 13, 30, 0.5)',
            '--bg-card-hover': 'rgba(50, 20, 55, 0.5)',
            '--card-border': 'rgba(249, 168, 212, 0.12)',
            '--card-border-hover': 'rgba(249, 168, 212, 0.4)',
            '--accent': '#f9a8d4',
            '--accent-dim': 'rgba(249, 168, 212, 0.15)',
            '--accent-glow': 'rgba(249, 168, 212, 0.25)',
            '--accent-hover': '#f472b6',
            '--purple': '#e879f9',
            '--purple-dim': 'rgba(232, 121, 249, 0.15)',
            '--text-main': '#fdf2f8',
            '--text-secondary': '#fbcfe8',
            '--text-muted': '#ec4899',
            '--text-dim': '#9d174d',
            '--success': '#86efac',
            '--warning': '#fde68a',
            '--error': '#fda4af',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #4a1942 0%, #1a0d1e 90%)',
        titlebar: 'linear-gradient(90deg, #e879f9 0%, #4a1942 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #ec4899 0%, #7e22ce 60%, transparent 100%)',
        meshOpacity: 0.3,
        candleUp: '#f9a8d4',
        candleDown: '#c084fc',
    },

    // NATURE
    autumn: {
        name: 'Autumn Harvest',
        description: 'Nature · Warm amber and russet',
        category: 'image',
        preview: ['#1a0f00', '#d97706', '#92400e', '#451a03'],
        backgroundImage: './assets/themes/autumn_theme.png',
        vars: {
            '--bg-dark': '#1a0f00',
            '--bg-card': 'rgba(26, 15, 0, 0.5)',
            '--bg-card-hover': 'rgba(45, 25, 0, 0.5)',
            '--card-border': 'rgba(217, 119, 6, 0.12)',
            '--card-border-hover': 'rgba(217, 119, 6, 0.4)',
            '--accent': '#d97706',
            '--accent-dim': 'rgba(217, 119, 6, 0.15)',
            '--accent-glow': 'rgba(217, 119, 6, 0.25)',
            '--accent-hover': '#b45309',
            '--purple': '#fbbf24',
            '--purple-dim': 'rgba(251, 191, 36, 0.15)',
            '--text-main': '#fef3c7',
            '--text-secondary': '#fde68a',
            '--text-muted': '#b45309',
            '--text-dim': '#78350f',
            '--success': '#84cc16',
            '--warning': '#f59e0b',
            '--error': '#b91c1c',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #451a03 0%, #1a0f00 90%)',
        titlebar: 'linear-gradient(90deg, #92400e 0%, #1a0f00 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #b45309 0%, #451a03 60%, transparent 100%)',
        meshOpacity: 0.35,
        candleUp: '#d97706',
        candleDown: '#92400e',
    },

    aurora: {
        name: 'Aurora Borealis',
        description: 'Nature · Northern lights shimmer',
        category: 'image',
        preview: ['#020617', '#34d399', '#a78bfa', '#064e3b'],
        backgroundImage: './assets/themes/aurora_theme.png',
        vars: {
            '--bg-dark': '#020617',
            '--bg-card': 'rgba(2, 6, 23, 0.5)',
            '--bg-card-hover': 'rgba(6, 30, 40, 0.5)',
            '--card-border': 'rgba(52, 211, 153, 0.12)',
            '--card-border-hover': 'rgba(52, 211, 153, 0.4)',
            '--accent': '#34d399',
            '--accent-dim': 'rgba(52, 211, 153, 0.15)',
            '--accent-glow': 'rgba(52, 211, 153, 0.25)',
            '--accent-hover': '#10b981',
            '--purple': '#a78bfa',
            '--purple-dim': 'rgba(167, 139, 250, 0.15)',
            '--text-main': '#ecfdf5',
            '--text-secondary': '#a7f3d0',
            '--text-muted': '#059669',
            '--text-dim': '#064e3b',
            '--success': '#34d399',
            '--warning': '#fbbf24',
            '--error': '#f87171',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #064e3b 0%, #020617 90%)',
        titlebar: 'linear-gradient(90deg, #10b981 0%, #7c3aed 100%)',
        meshGradient: 'radial-gradient(circle at 20% 20%, #10b981 0%, #6d28d9 50%, transparent 100%)',
        meshOpacity: 0.4,
        candleUp: '#34d399',
        candleDown: '#a78bfa',
    },

    tropical: {
        name: 'Tropical Reef',
        description: 'Nature · Bright turquoise and coral',
        category: 'image',
        preview: ['#042f2e', '#2dd4bf', '#f472b6', '#134e4a'],
        backgroundImage: './assets/themes/tropical_theme.png',
        vars: {
            '--bg-dark': '#042f2e',
            '--bg-card': 'rgba(4, 47, 46, 0.5)',
            '--bg-card-hover': 'rgba(19, 78, 74, 0.5)',
            '--card-border': 'rgba(45, 212, 191, 0.12)',
            '--card-border-hover': 'rgba(45, 212, 191, 0.4)',
            '--accent': '#2dd4bf',
            '--accent-dim': 'rgba(45, 212, 191, 0.15)',
            '--accent-glow': 'rgba(45, 212, 191, 0.25)',
            '--accent-hover': '#14b8a6',
            '--purple': '#f472b6',
            '--purple-dim': 'rgba(244, 114, 182, 0.15)',
            '--text-main': '#f0fdfa',
            '--text-secondary': '#99f6e4',
            '--text-muted': '#14b8a6',
            '--text-dim': '#0f766e',
            '--success': '#22d3ee',
            '--warning': '#fbbf24',
            '--error': '#fb7185',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #134e4a 0%, #042f2e 90%)',
        titlebar: 'linear-gradient(90deg, #0d9488 0%, #042f2e 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #14b8a6 0%, #0e7490 60%, transparent 100%)',
        meshOpacity: 0.35,
        candleUp: '#2dd4bf',
        candleDown: '#f472b6',
    },

    // CREATIVE
    synthwave: {
        name: 'Synthwave',
        description: '80s retrowave neon',
        category: 'image',
        preview: ['#0d001a', '#e879f9', '#06b6d4', '#2e0854'],
        backgroundImage: './assets/themes/synthwave_theme.png',
        vars: {
            '--bg-dark': '#0d001a',
            '--bg-card': 'rgba(13, 0, 26, 0.6)',
            '--bg-card-hover': 'rgba(30, 0, 50, 0.6)',
            '--card-border': 'rgba(232, 121, 249, 0.12)',
            '--card-border-hover': 'rgba(232, 121, 249, 0.4)',
            '--accent': '#e879f9',
            '--accent-dim': 'rgba(232, 121, 249, 0.15)',
            '--accent-glow': 'rgba(232, 121, 249, 0.25)',
            '--accent-hover': '#d946ef',
            '--purple': '#06b6d4',
            '--purple-dim': 'rgba(6, 182, 212, 0.15)',
            '--text-main': '#fdf4ff',
            '--text-secondary': '#f0abfc',
            '--text-muted': '#a855f7',
            '--text-dim': '#6b21a8',
            '--success': '#22d3ee',
            '--warning': '#fde68a',
            '--error': '#fb7185',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #2e0854 0%, #0d001a 90%)',
        titlebar: 'linear-gradient(90deg, #d946ef 0%, #0891b2 100%)',
        meshGradient: 'radial-gradient(circle at 0% 100%, #d946ef 0%, #0891b2 50%, transparent 100%)',
        meshOpacity: 0.35,
        candleUp: '#e879f9',
        candleDown: '#06b6d4',
    },

    bloodmoon: {
        name: 'Blood Moon',
        description: 'Deep crimson eclipse',
        category: 'image',
        preview: ['#0a0000', '#ef4444', '#7f1d1d', '#450a0a'],
        backgroundImage: './assets/themes/bloodmoon_theme.png',
        vars: {
            '--bg-dark': '#0a0000',
            '--bg-card': 'rgba(10, 0, 0, 0.6)',
            '--bg-card-hover': 'rgba(30, 5, 5, 0.6)',
            '--card-border': 'rgba(239, 68, 68, 0.12)',
            '--card-border-hover': 'rgba(239, 68, 68, 0.4)',
            '--accent': '#ef4444',
            '--accent-dim': 'rgba(239, 68, 68, 0.15)',
            '--accent-glow': 'rgba(239, 68, 68, 0.25)',
            '--accent-hover': '#dc2626',
            '--purple': '#fca5a5',
            '--purple-dim': 'rgba(252, 165, 165, 0.15)',
            '--text-main': '#fef2f2',
            '--text-secondary': '#fecaca',
            '--text-muted': '#b91c1c',
            '--text-dim': '#7f1d1d',
            '--success': '#f87171',
            '--warning': '#fbbf24',
            '--error': '#991b1b',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #450a0a 0%, #0a0000 90%)',
        titlebar: 'linear-gradient(90deg, #991b1b 0%, #0a0000 100%)',
        meshGradient: 'radial-gradient(circle at 50% 0%, #991b1b 0%, #0a0000 60%, transparent 100%)',
        meshOpacity: 0.4,
        candleUp: '#ef4444',
        candleDown: '#7f1d1d',
    },

    dracula: {
        name: 'Dracula',
        description: 'Classic dark purple theme',
        category: 'image',
        preview: ['#282a36', '#bd93f9', '#ff79c6', '#44475a'],
        backgroundImage: './assets/themes/dracula_theme.png',
        vars: {
            '--bg-dark': '#282a36',
            '--bg-card': 'rgba(40, 42, 54, 0.6)',
            '--bg-card-hover': 'rgba(68, 71, 90, 0.6)',
            '--card-border': 'rgba(189, 147, 249, 0.12)',
            '--card-border-hover': 'rgba(189, 147, 249, 0.4)',
            '--accent': '#bd93f9',
            '--accent-dim': 'rgba(189, 147, 249, 0.15)',
            '--accent-glow': 'rgba(189, 147, 249, 0.25)',
            '--accent-hover': '#a67bf5',
            '--purple': '#ff79c6',
            '--purple-dim': 'rgba(255, 121, 198, 0.15)',
            '--text-main': '#f8f8f2',
            '--text-secondary': '#f8f8f2',
            '--text-muted': '#6272a4',
            '--text-dim': '#44475a',
            '--success': '#50fa7b',
            '--warning': '#f1fa8c',
            '--error': '#ff5555',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #44475a 0%, #282a36 90%)',
        titlebar: 'linear-gradient(90deg, #6272a4 0%, #282a36 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #44475a 0%, #282a36 60%, transparent 100%)',
        meshOpacity: 0.3,
        candleUp: '#bd93f9',
        candleDown: '#ff5555',
    },

    nord: {
        name: 'Nord',
        description: 'Cool Scandinavian blue-gray',
        category: 'color',
        preview: ['#2e3440', '#88c0d0', '#81a1c1', '#3b4252'],
        vars: {
            '--bg-dark': '#2e3440',
            '--bg-card': 'rgba(46, 52, 64, 0.6)',
            '--bg-card-hover': 'rgba(59, 66, 82, 0.6)',
            '--card-border': 'rgba(136, 192, 208, 0.12)',
            '--card-border-hover': 'rgba(136, 192, 208, 0.4)',
            '--accent': '#88c0d0',
            '--accent-dim': 'rgba(136, 192, 208, 0.15)',
            '--accent-glow': 'rgba(136, 192, 208, 0.25)',
            '--accent-hover': '#81a1c1',
            '--purple': '#b48ead',
            '--purple-dim': 'rgba(180, 142, 173, 0.15)',
            '--text-main': '#eceff4',
            '--text-secondary': '#d8dee9',
            '--text-muted': '#81a1c1',
            '--text-dim': '#4c566a',
            '--success': '#a3be8c',
            '--warning': '#ebcb8b',
            '--error': '#bf616a',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #3b4252 0%, #2e3440 90%)',
        titlebar: 'linear-gradient(90deg, #4c566a 0%, #2e3440 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #434c5e 0%, #2e3440 60%, transparent 100%)',
        meshOpacity: 0.25,
        candleUp: '#88c0d0',
        candleDown: '#bf616a',
    },

    jade: {
        name: 'Jade Empire',
        description: 'Rich jade green luxury',
        category: 'color',
        preview: ['#021a0a', '#059669', '#10b981', '#064e3b'],
        vars: {
            '--bg-dark': '#021a0a',
            '--bg-card': 'rgba(2, 26, 10, 0.5)',
            '--bg-card-hover': 'rgba(6, 50, 30, 0.5)',
            '--card-border': 'rgba(5, 150, 105, 0.12)',
            '--card-border-hover': 'rgba(5, 150, 105, 0.4)',
            '--accent': '#059669',
            '--accent-dim': 'rgba(5, 150, 105, 0.15)',
            '--accent-glow': 'rgba(5, 150, 105, 0.25)',
            '--accent-hover': '#047857',
            '--purple': '#34d399',
            '--purple-dim': 'rgba(52, 211, 153, 0.15)',
            '--text-main': '#ecfdf5',
            '--text-secondary': '#a7f3d0',
            '--text-muted': '#059669',
            '--text-dim': '#064e3b',
            '--success': '#10b981',
            '--warning': '#fbbf24',
            '--error': '#dc2626',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #064e3b 0%, #021a0a 90%)',
        titlebar: 'linear-gradient(90deg, #047857 0%, #021a0a 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #047857 0%, #021a0a 60%, transparent 100%)',
        meshOpacity: 0.35,
        candleUp: '#059669',
        candleDown: '#dc2626',
    },

    copper: {
        name: 'Copper Rose',
        description: 'Warm copper and bronze luxury',
        category: 'image',
        preview: ['#0d0604', '#c2734c', '#a0522d', '#3d1c0a'],
        backgroundImage: './assets/themes/copper_theme.png',
        vars: {
            '--bg-dark': '#0d0604',
            '--bg-card': 'rgba(13, 6, 4, 0.6)',
            '--bg-card-hover': 'rgba(30, 15, 8, 0.6)',
            '--card-border': 'rgba(194, 115, 76, 0.12)',
            '--card-border-hover': 'rgba(194, 115, 76, 0.4)',
            '--accent': '#c2734c',
            '--accent-dim': 'rgba(194, 115, 76, 0.15)',
            '--accent-glow': 'rgba(194, 115, 76, 0.25)',
            '--accent-hover': '#a0522d',
            '--purple': '#dda15e',
            '--purple-dim': 'rgba(221, 161, 94, 0.15)',
            '--text-main': '#fef7ee',
            '--text-secondary': '#e8c9a4',
            '--text-muted': '#a0522d',
            '--text-dim': '#5c2d0a',
            '--success': '#84cc16',
            '--warning': '#dda15e',
            '--error': '#991b1b',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #3d1c0a 0%, #0d0604 90%)',
        titlebar: 'linear-gradient(90deg, #a0522d 0%, #3d1c0a 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #a0522d 0%, #0d0604 60%, transparent 100%)',
        meshOpacity: 0.3,
        candleUp: '#c2734c',
        candleDown: '#991b1b',
    },

    lavender: {
        name: 'Lavender Haze',
        description: 'Soft dreamy purple mist',
        category: 'color',
        preview: ['#110d1a', '#a78bfa', '#c4b5fd', '#1e1b4b'],
        vars: {
            '--bg-dark': '#110d1a',
            '--bg-card': 'rgba(17, 13, 26, 0.5)',
            '--bg-card-hover': 'rgba(30, 27, 55, 0.5)',
            '--card-border': 'rgba(167, 139, 250, 0.12)',
            '--card-border-hover': 'rgba(167, 139, 250, 0.4)',
            '--accent': '#a78bfa',
            '--accent-dim': 'rgba(167, 139, 250, 0.15)',
            '--accent-glow': 'rgba(167, 139, 250, 0.25)',
            '--accent-hover': '#8b5cf6',
            '--purple': '#c4b5fd',
            '--purple-dim': 'rgba(196, 181, 253, 0.15)',
            '--text-main': '#ede9fe',
            '--text-secondary': '#c4b5fd',
            '--text-muted': '#7c3aed',
            '--text-dim': '#4c1d95',
            '--success': '#86efac',
            '--warning': '#fde68a',
            '--error': '#f87171',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #1e1b4b 0%, #110d1a 90%)',
        titlebar: 'linear-gradient(90deg, #7c3aed 0%, #1e1b4b 100%)',
        meshGradient: 'radial-gradient(circle at 30% 0%, #7c3aed 0%, #312e81 60%, transparent 100%)',
        meshOpacity: 0.35,
        candleUp: '#a78bfa',
        candleDown: '#f87171',
    },

    ember: {
        name: 'Ember',
        description: 'Molten fire and lava glow',
        category: 'image',
        preview: ['#0d0200', '#f59e0b', '#ef4444', '#451a03'],
        backgroundImage: './assets/themes/ember_theme.png',
        vars: {
            '--bg-dark': '#0d0200',
            '--bg-card': 'rgba(13, 2, 0, 0.6)',
            '--bg-card-hover': 'rgba(30, 8, 0, 0.6)',
            '--card-border': 'rgba(245, 158, 11, 0.12)',
            '--card-border-hover': 'rgba(245, 158, 11, 0.4)',
            '--accent': '#f59e0b',
            '--accent-dim': 'rgba(245, 158, 11, 0.15)',
            '--accent-glow': 'rgba(245, 158, 11, 0.25)',
            '--accent-hover': '#d97706',
            '--purple': '#ef4444',
            '--purple-dim': 'rgba(239, 68, 68, 0.15)',
            '--text-main': '#fef9c3',
            '--text-secondary': '#fde68a',
            '--text-muted': '#b45309',
            '--text-dim': '#78350f',
            '--success': '#fbbf24',
            '--warning': '#f59e0b',
            '--error': '#991b1b',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #451a03 0%, #0d0200 90%)',
        titlebar: 'linear-gradient(90deg, #dc2626 0%, #d97706 100%)',
        meshGradient: 'radial-gradient(circle at 0% 100%, #dc2626 0%, #d97706 40%, transparent 100%)',
        meshOpacity: 0.35,
        candleUp: '#f59e0b',
        candleDown: '#991b1b',
    },

    neontokyo: {
        name: 'Neon Tokyo',
        description: 'Vibrant magenta and cyan neon',
        category: 'image',
        preview: ['#070012', '#ec4899', '#22d3ee', '#3b0764'],
        backgroundImage: './assets/themes/neontokyo_theme.png',
        vars: {
            '--bg-dark': '#070012',
            '--bg-card': 'rgba(7, 0, 18, 0.6)',
            '--bg-card-hover': 'rgba(20, 0, 40, 0.6)',
            '--card-border': 'rgba(236, 72, 153, 0.12)',
            '--card-border-hover': 'rgba(236, 72, 153, 0.4)',
            '--accent': '#ec4899',
            '--accent-dim': 'rgba(236, 72, 153, 0.15)',
            '--accent-glow': 'rgba(236, 72, 153, 0.25)',
            '--accent-hover': '#db2777',
            '--purple': '#22d3ee',
            '--purple-dim': 'rgba(34, 211, 238, 0.15)',
            '--text-main': '#fdf2f8',
            '--text-secondary': '#fbcfe8',
            '--text-muted': '#be185d',
            '--text-dim': '#831843',
            '--success': '#22d3ee',
            '--warning': '#fde68a',
            '--error': '#f43f5e',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #3b0764 0%, #070012 90%)',
        titlebar: 'linear-gradient(90deg, #ec4899 0%, #0891b2 100%)',
        meshGradient: 'radial-gradient(circle at 80% 20%, #db2777 0%, #0891b2 60%, transparent 100%)',
        meshOpacity: 0.3,
        candleUp: '#ec4899',
        candleDown: '#22d3ee',
    },

    monochrome: {
        name: 'Monochrome',
        description: 'Clean grayscale editorial',
        category: 'color',
        preview: ['#111111', '#e5e7eb', '#9ca3af', '#1f1f1f'],
        vars: {
            '--bg-dark': '#111111',
            '--bg-card': 'rgba(17, 17, 17, 0.6)',
            '--bg-card-hover': 'rgba(31, 31, 31, 0.6)',
            '--card-border': 'rgba(229, 231, 235, 0.08)',
            '--card-border-hover': 'rgba(229, 231, 235, 0.3)',
            '--accent': '#e5e7eb',
            '--accent-dim': 'rgba(229, 231, 235, 0.1)',
            '--accent-glow': 'rgba(229, 231, 235, 0.15)',
            '--accent-hover': '#d1d5db',
            '--purple': '#9ca3af',
            '--purple-dim': 'rgba(156, 163, 175, 0.1)',
            '--text-main': '#f3f4f6',
            '--text-secondary': '#d1d5db',
            '--text-muted': '#6b7280',
            '--text-dim': '#374151',
            '--success': '#d1d5db',
            '--warning': '#9ca3af',
            '--error': '#6b7280',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #1f1f1f 0%, #111111 90%)',
        titlebar: 'linear-gradient(90deg, #374151 0%, #111111 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #1f2937 0%, #111111 60%, transparent 100%)',
        meshOpacity: 0.2,
        candleUp: '#e5e7eb',
        candleDown: '#6b7280',
    },

    cherry: {
        name: 'Cherry Cola',
        description: 'Deep cherry red and dark cola',
        category: 'image',
        preview: ['#0d0007', '#e11d48', '#be123c', '#4c0519'],
        backgroundImage: './assets/themes/cherry_theme.png',
        vars: {
            '--bg-dark': '#0d0007',
            '--bg-card': 'rgba(13, 0, 7, 0.6)',
            '--bg-card-hover': 'rgba(30, 0, 15, 0.6)',
            '--card-border': 'rgba(225, 29, 72, 0.12)',
            '--card-border-hover': 'rgba(225, 29, 72, 0.4)',
            '--accent': '#e11d48',
            '--accent-dim': 'rgba(225, 29, 72, 0.15)',
            '--accent-glow': 'rgba(225, 29, 72, 0.25)',
            '--accent-hover': '#be123c',
            '--purple': '#fb7185',
            '--purple-dim': 'rgba(251, 113, 133, 0.15)',
            '--text-main': '#fff1f2',
            '--text-secondary': '#fda4af',
            '--text-muted': '#be123c',
            '--text-dim': '#881337',
            '--success': '#fb923c',
            '--warning': '#fbbf24',
            '--error': '#9f1239',
        },
        sidebar: 'radial-gradient(circle at 0% 0%, #4c0519 0%, #0d0007 90%)',
        titlebar: 'linear-gradient(90deg, #be123c 0%, #4c0519 100%)',
        meshGradient: 'radial-gradient(circle at 0% 0%, #be123c 0%, #4c0519 60%, transparent 100%)',
        meshOpacity: 0.3,
        candleUp: '#e11d48',
        candleDown: '#450a0a',
    },
};

// ═══════════════════════════════════════════════════════════
// THEME ENGINE
// ═══════════════════════════════════════════════════════════

function getThemes() {
    return THEMES;
}

function getActiveThemeId() {
    return localStorage.getItem('tradebot-theme') || 'obsidian';
}

/** Async: get the filesystem-persisted theme (authoritative source) */
async function getPersistedThemeId() {
    try {
        if (window.api && window.api.invoke) {
            const fsTheme = await window.api.invoke('get-theme');
            if (fsTheme) {
                // Sync localStorage with filesystem
                localStorage.setItem('tradebot-theme', fsTheme);
                return fsTheme;
            }
        }
    } catch (_) { /* fall through */ }
    return getActiveThemeId();
}

function applyTheme(themeId, _skipPersist = false) {
    // Handle 'random' — pick a random real theme each time
    if (themeId === 'random') {
        const realKeys = Object.keys(THEMES);
        const pick = realKeys[Math.floor(Math.random() * realKeys.length)];
        console.log(`[THEME] Random selected: ${pick}`);
        localStorage.setItem('tradebot-theme', 'random'); // keep 'random' so it re-rolls on next load
        try { if (window.api && window.api.invoke) window.api.invoke('save-theme', 'random'); } catch (_) { }
        applyTheme(pick, true); // _skipPersist = true so "random" isn't overwritten
        return;
    }

    const theme = THEMES[themeId];
    if (!theme) {
        console.warn(`[THEME] Unknown theme: ${themeId}`);
        return;
    }

    console.log(`[THEME] Applying: ${theme.name}`);

    // 1. Set CSS variables on :root
    const root = document.documentElement;
    for (const [prop, value] of Object.entries(theme.vars)) {
        root.style.setProperty(prop, value);
    }

    // 2. Update sidebar gradient
    const sidebar = document.querySelector('#view-settings .w-72, [data-theme-sidebar]');
    // Main sidebar in dashboard
    const mainSidebar = document.querySelector('.flex.flex-col.mt-4.ml-5 > div:first-child');
    if (mainSidebar) {
        mainSidebar.style.background = theme.sidebar;
    }

    // 3. Update titlebar
    const titlebar = document.querySelector('.titlebar-drag');
    if (titlebar) {
        titlebar.style.background = theme.titlebar;
    }

    // 4. Background layers
    const bgSolid = document.querySelector('[data-theme-bg-solid]');
    const bgMesh = document.querySelector('[data-theme-bg-mesh]');
    const bgImage = document.getElementById('theme-bg-image');

    if (bgSolid) {
        bgSolid.style.backgroundColor = theme.vars['--bg-dark'];
    }

    if (bgMesh) {
        bgMesh.style.backgroundImage = theme.meshGradient;
        bgMesh.style.opacity = theme.meshOpacity;
    }

    // 5. Background image (for image themes)
    if (bgImage) {
        if (theme.backgroundImage) {
            bgImage.style.backgroundImage = `url('${theme.backgroundImage}')`;
            bgImage.style.display = 'block';
        } else {
            bgImage.style.backgroundImage = 'none';
            bgImage.style.display = 'none';
        }
    }

    // 5.5. Update panel gradient containers (Decisions Panel + System Logs)
    // These use hardcoded radial-gradient spot colors that need theme awareness
    const accentHover = theme.vars['--accent-hover'] || '#0d9488';
    const bgDark = theme.vars['--bg-dark'] || '#020617';
    const panelGradient = `radial-gradient(circle at 0% 0%, ${accentHover} 0%, ${bgDark} 70%)`;
    const panelContainers = document.querySelectorAll('#view-dashboard > div.flex-1, #view-dashboard > div.flex-\\[1\\.5\\]');
    // More robust: target the bottom panel containers by their structure
    const dashView = document.getElementById('view-dashboard');
    if (dashView) {
        const children = dashView.children;
        for (let i = 1; i < children.length; i++) { // skip first child (chart panel)
            const child = children[i];
            if (child.style && child.classList.contains('rounded-xl')) {
                child.style.background = panelGradient;
            }
        }
    }

    // 5.6. Update sidebar border and chart panel borders to use accent
    const accent = theme.vars['--accent'] || '#14b8a6';

    // 6. Persist (skip if called from random handler to preserve 'random' in storage)
    if (!_skipPersist) {
        localStorage.setItem('tradebot-theme', themeId);
        // Also persist to filesystem via IPC (authoritative)
        try {
            if (window.api && window.api.invoke) {
                window.api.invoke('save-theme', themeId);
            }
        } catch (_) { /* localStorage is the fallback */ }
    }

    // 7. Dispatch event so other components can react
    window.dispatchEvent(new CustomEvent('theme-changed', { detail: { themeId, theme } }));
}

// Auto-apply saved theme on load
document.addEventListener('DOMContentLoaded', () => {
    // Immediately apply localStorage theme (fast, prevents flash)
    const cachedTheme = getActiveThemeId();
    requestAnimationFrame(() => {
        applyTheme(cachedTheme, true); // _skipPersist=true to avoid re-saving
    });
    // Then check filesystem for authoritative theme (may differ if localStorage was cleared)
    getPersistedThemeId().then((fsTheme) => {
        if (fsTheme && fsTheme !== cachedTheme) {
            console.log(`[THEME] Filesystem override: ${fsTheme} (localStorage had: ${cachedTheme})`);
            applyTheme(fsTheme);
        }
    });
});

// Export for global access
window.ThemeEngine = { getThemes, getActiveThemeId, applyTheme, THEMES };
