 /** @type {import('tailwindcss').Config} */
 export default {
     darkMode: ["class"],
    content: ["./index.html", "./src/**/*.{html,js,jsx}"],
  theme: {
  	extend: {
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		fontFamily: {
  			sans: ['Outfit', 'sans-serif'],
  			mono: ['Space Mono', 'monospace'],
  		},
  		colors: {
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			},
  			// ATC custom colors
  			atc: {
  				bg: '#050b14',
  				'bg-secondary': '#080f1c',
  				panel: '#0d1e33',
  				'panel-alt': '#102240',
  				cyan: '#00c8ff',
  				green: '#00ffc8',
  				orange: '#ff6b35',
  				gold: '#ffd700',
  				danger: '#ff3b5c',
  				warning: '#ffaa00',
  				success: '#00e676',
  				purple: '#a855f7',
  				'text-primary': '#e8f4ff',
  				'text-secondary': '#7ba8c8',
  				'text-muted': '#4a7090',
  			}
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
}