<?php
/**
 * Plugin settings (options table), intentionally separate from content.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Settings wrapper with a well-known option name and predictable array shape.
 */
class TUSB_Settings {

	/**
	 * Option name.
	 */
	const OPTION = 'tusb_settings';

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		register_setting(
			'tusb_settings',
			self::OPTION,
			array(
				'type'              => 'array',
				'sanitize_callback' => array( __CLASS__, 'sanitize' ),
				'default'           => array(),
				'show_in_rest'      => false,
			)
		);
	}

	/**
	 * All settings.
	 *
	 * @return array
	 */
	public static function all() {
		$settings = get_option( self::OPTION, array() );
		return is_array( $settings ) ? $settings : array();
	}

	/**
	 * Get one top-level setting with default.
	 *
	 * @param string $key Key.
	 * @param mixed  $default Default.
	 * @return mixed
	 */
	public static function get( $key, $default = null ) {
		$settings = self::all();
		return array_key_exists( $key, $settings ) ? $settings[ $key ] : $default;
	}

	/**
	 * Update one top-level setting.
	 *
	 * @param string $key Key.
	 * @param mixed  $value Value.
	 * @return bool
	 */
	public static function set( $key, $value ) {
		$settings         = self::all();
		$settings[ $key ] = $value;
		return update_option( self::OPTION, $settings, false );
	}

	/**
	 * Sanitise the whole settings payload.
	 *
	 * @param mixed $input Input.
	 * @return array
	 */
	public static function sanitize( $input ) {
		if ( ! is_array( $input ) ) {
			return self::all();
		}
		$existing = self::all();
		$clean    = $existing;

		$bool_keys = array(
			'contact_form_active',
			'debug_mode',
			'welcome_dismissed',
		);
		foreach ( $bool_keys as $key ) {
			if ( array_key_exists( $key, $input ) ) {
				$clean[ $key ] = TUSB_Sanitizer::to_bool( $input[ $key ] );
			}
		}

		return $clean;
	}
}
