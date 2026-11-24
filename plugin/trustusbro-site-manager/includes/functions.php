<?php
/**
 * Shared helper functions.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Log a message when WP_DEBUG is on. Never writes outside the plugin's own log path.
 *
 * @param mixed $message Message or data.
 * @return void
 */
function tusb_log( $message ) {
	if ( ! defined( 'WP_DEBUG' ) || ! WP_DEBUG ) {
		return;
	}
	if ( is_array( $message ) || is_object( $message ) ) {
		$message = wp_json_encode( $message );
	}
	error_log( '[tusb] ' . $message ); // phpcs:ignore WordPress.PHP.DevelopmentFunctions.error_log_error_log
}

/**
 * Safe array access.
 *
 * @param array  $arr Source array.
 * @param string $key Key.
 * @param mixed  $default Fallback.
 * @return mixed
 */
function tusb_arr( $arr, $key, $default = null ) {
	if ( ! is_array( $arr ) || ! array_key_exists( $key, $arr ) ) {
		return $default;
	}
	return $arr[ $key ];
}

/**
 * Build a URL to a Site Manager admin screen.
 *
 * @param string $view View slug.
 * @param array  $args Extra query args.
 * @return string
 */
function tusb_admin_url( $view = 'dashboard', $args = array() ) {
	$args = array_merge( array( 'page' => 'tusb-' . $view ), $args );
	return add_query_arg( $args, admin_url( 'admin.php' ) );
}

/**
 * Front-end preview URL for a document.
 *
 * @param string $doc_key Document key.
 * @param array  $args Extra args.
 * @return string
 */
function tusb_preview_url( $doc_key, $args = array() ) {
	$url = add_query_arg(
		array_merge(
			array(
				'tusb_preview' => $doc_key,
			),
			$args
		),
		home_url( '/' )
	);
	$url = add_query_arg( 'tusb_nonce', wp_create_nonce( 'tusb_preview' ), $url );
	return $url;
}

/**
 * Is the current request a Site Manager editor preview?
 *
 * @return bool
 */
function tusb_is_preview() {
	if ( ! isset( $_GET['tusb_preview'] ) ) { // phpcs:ignore WordPress.Security.NonceVerification.Recommended
		return false;
	}
	if ( ! is_user_logged_in() || ! current_user_can( 'edit_posts' ) ) {
		return false;
	}
	$nonce = isset( $_GET['tusb_nonce'] ) ? sanitize_text_field( wp_unslash( $_GET['tusb_nonce'] ) ) : ''; // phpcs:ignore WordPress.Security.NonceVerification.Recommended
	return (bool) wp_verify_nonce( $nonce, 'tusb_preview' );
}

/**
 * Current preview document key, if any.
 *
 * @return string
 */
function tusb_preview_doc() {
	if ( ! tusb_is_preview() ) {
		return '';
	}
	return sanitize_key( wp_unslash( $_GET['tusb_preview'] ) ); // phpcs:ignore WordPress.Security.NonceVerification.Recommended
}

/**
 * Decode a JSON string into an array, returning array() on failure.
 *
 * @param string $json JSON string.
 * @return array
 */
function tusb_json_decode( $json ) {
	if ( ! is_string( $json ) || '' === trim( $json ) ) {
		return array();
	}
	$decoded = json_decode( $json, true );
	return is_array( $decoded ) ? $decoded : array();
}

/**
 * Encode data for storage in post_content.
 *
 * @param array $data Data.
 * @return string
 */
function tusb_json_encode( $data ) {
	return wp_json_encode( $data, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT );
}

/**
 * Human readable "2 minutes ago" style date, falling back to formatted date.
 *
 * @param int $timestamp Unix timestamp.
 * @return string
 */
function tusb_time_diff( $timestamp ) {
	$timestamp = (int) $timestamp;
	if ( $timestamp <= 0 ) {
		return __( 'never', 'trustusbro-site-manager' );
	}
	return sprintf(
		/* translators: %s: human readable time difference. */
		__( '%s ago', 'trustusbro-site-manager' ),
		human_time_diff( $timestamp, time() )
	);
}

/**
 * Sanitise a CSS length value such as 16px, 1.5rem, 60ch, 0.
 *
 * @param string $value Raw value.
 * @param string $fallback Fallback value.
 * @return string
 */
function tusb_sanitize_css_length( $value, $fallback = '' ) {
	$value = trim( (string) $value );
	if ( '' === $value ) {
		return $fallback;
	}
	if ( preg_match( '/^(0|(\d+(\.\d+)?)(px|rem|em|%|vh|vw|ch|ex|pt|clamp\([^)]+\)|calc\([^)]+\)))$/i', $value ) ) {
		return $value;
	}
	return $fallback;
}

/**
 * Sanitise a CSS colour: hex, rgb(a), hsl(a), or a var() reference.
 *
 * @param string $value Raw value.
 * @return string
 */
function tusb_sanitize_color( $value ) {
	$value = trim( (string) $value );
	if ( '' === $value ) {
		return '';
	}
	if ( preg_match( '/^#([0-9a-f]{3,8})$/i', $value ) ) {
		return $value;
	}
	if ( preg_match( '/^rgba?\(\s*[\d.%\s,]+\)$/i', $value ) ) {
		return $value;
	}
	if ( preg_match( '/^hsla?\(\s*[\d.%\s,a-z]+\)$/i', $value ) ) {
		return $value;
	}
	if ( preg_match( '/^var\(\s*--[a-z0-9_-]+\s*(,\s*[^)]+)?\)$/i', $value ) ) {
		return $value;
	}
	if ( 'transparent' === strtolower( $value ) || 'currentColor' === $value ) {
		return $value;
	}
	return '';
}

/**
 * Sanitise a font-family stack (letters, digits, spaces, commas, quotes, hyphens).
 *
 * @param string $value Raw value.
 * @return string
 */
function tusb_sanitize_font_family( $value ) {
	$value = trim( wp_strip_all_tags( (string) $value ) );
	if ( '' === $value ) {
		return '';
	}
	if ( preg_match( '/^[A-Za-z0-9 ,\'"_\-\/]+$/', $value ) ) {
		return $value;
	}
	return '';
}

/**
 * Map of document keys to friendly labels (used by UI and revisions).
 *
 * @return array<string,string>
 */
function tusb_doc_labels() {
	return array(
		'home'         => __( 'Homepage', 'trustusbro-site-manager' ),
		'about'        => __( 'About page', 'trustusbro-site-manager' ),
		'services'     => __( 'Services', 'trustusbro-site-manager' ),
		'industries'   => __( 'Industries', 'trustusbro-site-manager' ),
		'case_studies' => __( 'Case studies', 'trustusbro-site-manager' ),
		'testimonials' => __( 'Testimonials', 'trustusbro-site-manager' ),
		'faq'          => __( 'FAQ', 'trustusbro-site-manager' ),
		'contact'      => __( 'Contact information', 'trustusbro-site-manager' ),
		'header'       => __( 'Header', 'trustusbro-site-manager' ),
		'footer'       => __( 'Footer', 'trustusbro-site-manager' ),
		'seo'          => __( 'SEO defaults', 'trustusbro-site-manager' ),
		'design'       => __( 'Design tokens', 'trustusbro-site-manager' ),
	);
}

/**
 * Friendly label for a document key.
 *
 * @param string $key Document key.
 * @return string
 */
function tusb_doc_label( $key ) {
	$labels = tusb_doc_labels();
	if ( isset( $labels[ $key ] ) ) {
		return $labels[ $key ];
	}
	return ucwords( str_replace( array( '_', '-' ), ' ', (string) $key ) );
}

/**
 * Pages that can be edited visually (sections based).
 *
 * @return array<string,string>
 */
function tusb_page_docs() {
	return array(
		'home'  => __( 'Homepage', 'trustusbro-site-manager' ),
		'about' => __( 'About page', 'trustusbro-site-manager' ),
	);
}

/**
 * Collection documents (repeatable cards).
 *
 * @return array<string,string>
 */
function tusb_collection_docs() {
	return array(
		'services'     => __( 'Services', 'trustusbro-site-manager' ),
		'industries'   => __( 'Industries', 'trustusbro-site-manager' ),
		'case_studies' => __( 'Case studies', 'trustusbro-site-manager' ),
		'testimonials' => __( 'Testimonials', 'trustusbro-site-manager' ),
		'faq'          => __( 'FAQ', 'trustusbro-site-manager' ),
	);
}
