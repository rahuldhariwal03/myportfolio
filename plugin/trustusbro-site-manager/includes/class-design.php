<?php
/**
 * Design tokens.
 *
 * The plugin never imposes a design. It exposes a small set of CSS custom
 * properties that default to the active theme's own values (via var() chains),
 * so the approved TrustUsBro look is preserved exactly.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Design tokens.
 */
class TUSB_Design {

	/**
	 * Hook registration.
	 *
	 * @return void
	 */
	public function hooks() {
		add_action( 'wp_enqueue_scripts', array( $this, 'enqueue' ), 20 );
		add_action( 'wp_head', array( $this, 'inline_tokens' ), 5 );
		add_filter( 'body_class', array( $this, 'body_class' ) );
	}

	/**
	 * Saved design tokens merged with schema defaults.
	 *
	 * @return array
	 */
	public static function tokens() {
		$store  = tusb()->module( 'store' );
		$values = $store ? $store->resolve( 'design', 'published' ) : TUSB_Schema::defaults( 'design' );
		return is_array( $values ) ? $values : array();
	}

	/**
	 * Get one token.
	 *
	 * @param string $key Key.
	 * @param string $default Default.
	 * @return string
	 */
	public static function token( $key, $default = '' ) {
		$tokens = self::tokens();
		$value  = isset( $tokens[ $key ] ) ? $tokens[ $key ] : '';
		if ( '' === $value || null === $value ) {
			return $default;
		}
		return is_scalar( $value ) ? (string) $value : $default;
	}

	/**
	 * Build the CSS custom property map. Empty values fall back to the theme.
	 *
	 * Each property is published twice:
	 *  - --tusb-* is the plugin's own namespace, safe to use anywhere.
	 *  - A var() chain references common theme variables so an unset token
	 *    inherits the active theme's palette instead of inventing one.
	 *
	 * @return array<string,string>
	 */
	public static function css_vars() {
		$fallback_theme = array(
			'color_text'      => 'var(--wp--preset--color--foreground, var(--color-text, var(--text, #111111)))',
			'color_heading'   => 'var(--wp--preset--color--foreground, var(--color-heading, var(--text, #111111)))',
			'color_muted'     => 'var(--wp--preset--color--gray-600, var(--color-muted, #6b6b6b))',
			'color_accent'    => 'var(--wp--preset--color--primary, var(--color-accent, #ff6a00))',
			'color_accent_text' => 'var(--wp--preset--color--background, var(--color-on-accent, #ffffff))',
			'color_surface'   => 'var(--wp--preset--color--base-2, var(--color-surface, #ffffff))',
			'color_border'    => 'var(--wp--preset--color--gray-200, var(--color-border, rgba(0,0,0,0.12)))',
			'color_bg'        => 'var(--wp--preset--color--base, var(--color-bg, #ffffff))',
			'font_body'       => 'var(--wp--preset--font-family--body, var(--font-body, inherit))',
			'font_heading'    => 'var(--wp--preset--font-family--heading, var(--font-heading, inherit))',
			'font_mono'       => 'var(--wp--preset--font-family--monospace, ui-monospace, monospace)',
			'radius'          => '0',
			'container_width' => '1280px',
			'section_space'   => '96px',
		);

		$vars = array();
		foreach ( $fallback_theme as $key => $fallback ) {
			$value = self::token( $key, '' );
			$vars[ '--tusb-' . str_replace( '_', '-', $key ) ] = '' !== $value ? $value : $fallback;
		}

		// Convenience aliases used by the templates.
		$radius = self::token( 'radius', '0' );
		$button_radius = array(
			'square' => $radius,
			'soft'   => '4px',
			'pill'   => '999px',
		);
		$style = self::token( 'button_style', 'square' );
		$vars['--tusb-button-radius'] = isset( $button_radius[ $style ] ) ? $button_radius[ $style ] : $radius;

		return $vars;
	}

	/**
	 * Print the tokens as an inline style block.
	 *
	 * @return void
	 */
	public function inline_tokens() {
		$vars = self::css_vars();
		$css  = ':root{';
		foreach ( $vars as $name => $value ) {
			$css .= $name . ':' . $value . ';';
		}
		$css .= '}';

		/**
		 * Filter the generated token CSS before printing.
		 *
		 * @param string $css CSS.
		 * @param array  $vars Variables.
		 */
		$css = apply_filters( 'tusb_inline_css', $css, $vars );

		printf( "<style id=\"tusb-design-tokens\">%s</style>\n", $css ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- CSS is built from sanitised tokens.
	}

	/**
	 * Load front-end styles.
	 *
	 * @return void
	 */
	public function enqueue() {
		$suffix = ( defined( 'SCRIPT_DEBUG' ) && SCRIPT_DEBUG ) ? '' : '.min';
		$css    = 'assets/css/site' . $suffix . '.css';
		$path   = TUSB_DIR . $css;

		if ( ! file_exists( $path ) ) {
			$css = 'assets/css/site.css';
		}

		wp_enqueue_style(
			'tusb-site',
			TUSB_URL . $css,
			array(),
			TUSB_VERSION
		);

		wp_enqueue_script(
			'tusb-site',
			TUSB_URL . 'assets/js/site.js',
			array(),
			TUSB_VERSION,
			true
		);
	}

	/**
	 * Add body classes.
	 *
	 * @param array $classes Classes.
	 * @return array
	 */
	public function body_class( $classes ) {
		$classes[] = 'tusb-active';
		if ( ! tusb_preview_doc() && self::token( 'show_branding', '1' ) ) {
			$classes[] = 'tusb-branding';
		}
		if ( tusb_preview_doc() ) {
			$classes[] = 'tusb-preview';
		}
		return $classes;
	}
}
