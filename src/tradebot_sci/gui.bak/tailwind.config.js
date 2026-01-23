/** @type {import('tailwindcss').Config} */
module.exports = {
    content: ["./*.{html,js}"],
    theme: {
        extend: {
            colors: {
                primary: '#38bdf8', // Cyan 400
                'panel-dark': '#0f172a', // Slate 900
                'border-dark': '#1e293b', // Slate 800
                'accent-green': '#4ade80', // Green 400
                'accent-red': '#f87171', // Red 400
                'accent-yellow': '#fbbf24', // Amber 400
            },
            fontFamily: {
                'mono': ['Consolas', 'Monaco', 'Courier New', 'monospace'],
            }
        },
    },
    plugins: [],
}
