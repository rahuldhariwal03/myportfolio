<?php
/**
 * Compatibility checks and health reporting.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Compatibility.
 */
class TUSB_Compat {

	/**
	 * Minimum PHP version.
	 */
	const MIN_PHP = '7.4';

	/**
	 * Minimum WordPress version.
	 */
	const MIN_WP = '6.0';

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		add_action( 'admin_notices', array( $this, 'notices' ) );
		add_filter( 'site_status_tests', array( $this, 'site_health_tests' ) );
	}

	/**
	 * Collect compatibility results.
	 *
	 * @return array
	 */
	public static function report() {
		global $wp_version;

		$php_ok = version_compare( PHP_VERSION, self::MIN_PHP, '>=' );
		$wp_ok  = version_compare( (string) $wp_version, self::MIN_WP, '>=' );
		$db_ok  = self::database_ok();

		$checks = array(
			'php' => array(
				'label'  => __( 'PHP version', 'trustusbro-site-manager' ),
				'value'  => PHP_VERSION,
				'need'   => sprintf( '%s+', self::MIN_PHP ),
				'ok'     => $php_ok,
				'advice' => __( 'Ask your host to switch to PHP 7.4 or newer (8.1+ recommended).', 'trustusbro-site-manager' ),
			),
			'wp'  => array(
				'label'  => __( 'WordPress version', 'trustusbro-site-manager' ),
				'value'  => (string) $wp_version,
				'need'   => sprintf( '%s+', self::MIN_WP ),
				'ok'     => $wp_ok,
				'advice' => __( 'Update WordPress from Dashboard → Updates.', 'trustusbro-site-manager' ),
			),
			'db'  => array(
				'label'  => __( 'Database writes', 'trustusbro-site-manager' ),
				'value'  => $db_ok ? __( 'Available', 'trustusbro-site-manager' ) : __( 'Blocked', 'trustusbro-site-manager' ),
				'need'   => __( 'Available', 'trustusbro-site-manager' ),
				'ok'     => $db_ok,
				'advice' => __( 'The database user needs INSERT/UPDATE permissions on wp_posts and wp_postmeta.', 'trustusbro-site-manager' ),
			),
			'mbstring' => array(
				'label'  => __( 'Multibyte strings (mbstring)', 'trustusbro-site-manager' ),
				'value'  => function_exists( 'mb_strlen' ) ? __( 'Yes', 'trustusbro-site-manager' ) : __( 'No', 'trustusbro-site-manager' ),
				'need'   => __( 'Recommended', 'trustusbro-site-manager' ),
				'ok'     => function_exists( 'mb_strlen' ),
				'advice' => __( 'Without mbstring, long labels may be trimmed at the byte boundary. Everything else works.', 'trustusbro-site-manager' ),
			),
			'uploads' => array(
				'label'  => __( 'Uploads folder writable', 'trustusbro-site-manager' ),
				'value'  => self::uploads_writable() ? __( 'Yes', 'trustusbro-site-manager' ) : __( 'No', 'trustusbro-site-manager' ),
				'need'   => __( 'Yes', 'trustusbro-site-manager' ),
				'ok'     => self::uploads_writable(),
				'advice' => __( 'Image replacement needs a writable wp-content/uploads directory.', 'trustusbro-site-manager' ),
			),
		);

		$blocking = array_filter(
			$checks,
			static function ( $check, $key ) {
				return ! $check['ok'] && in_array( $key, array( 'php', 'wp', 'db' ), true );
			},
			ARRAY_FILTER_USE_BOTH
		);

		return array(
			'checks'          => $checks,
			'blocking'        => $blocking,
			'ok'              => empty( $blocking ),
			'wp_version'      => (string) $wp_version,
			'php_version'     => PHP_VERSION,
			'theme'           => self::theme_info(),
			'active_plugins'  => self::active_plugins(),
			'conflicts'       => self::seo_plugins(),
			'server'          => isset( $_SERVER['SERVER_SOFTWARE'] ) ? sanitize_text_field( wp_unslash( $_SERVER['SERVER_SOFTWARE'] ) ) : '',
			'memory_limit'    => (string) ini_get( 'memory_limit' ),
			'max_upload'      => (string) ini_get( 'upload_max_filesize' ),
		);
	}

	/**
	 * Can we write to the database?
	 *
	 * @return bool
	 */
	public static function database_ok() {
		global $wpdb;
		$probe = $wpdb->suppress_errors( true );
		// phpcs:ignore WordPress.DB.DirectDatabaseQuery
		$ok = $wpdb->query( $wpdb->prepare( "SELECT 1 FROM {$wpdb->posts} WHERE ID = %d", 0 ) );
		$wpdb->suppress_errors( $probe );
		return false !== $ok;
	}

	/**
	 * Are uploads writable?
	 *
	 * @return bool
	 */
	public static function uploads_writable() {
		$uploads = wp_upload_dir( null, false );
		if ( ! empty( $uploads['error'] ) ) {
			return false;
		}
		return wp_is_writable( $uploads['basedir'] );
	}

	/**
	 * Active theme information.
	 *
	 * @return array
	 */
	public static function theme_info() {
		$theme = wp_get_theme();
		return array(
			'name'    => $theme->get( 'Name' ),
			'version' => $theme->get( 'Version' ),
			'is_block'=> (bool) $theme->is_block_theme(),
			'slug'    => $theme->get_stylesheet(),
		);
	}

	/**
	 * Active plugins (name => version).
	 *
	 * @return array
	 */
	public static function active_plugins() {
		$out = array();
		$plugins = function_exists( 'get_plugins' ) ? get_plugins() : array();
		foreach ( (array) get_option( 'active_plugins', array() ) as $plugin ) {
			$out[ $plugin ] = isset( $plugins[ $plugin ] ) ? $plugins[ $plugin ]['Name'] . ' ' . $plugins[ $plugin ]['Version'] : $plugin;
		}
		return $out;
	}

	/**
	 * Detect SEO plugins whose output we must not duplicate.
	 *
	 * @return array
	 */
	public static function seo_plugins() {
		$detected = array();
		$map      = array(
			'wordpress-seo/wp-seo.php'            => 'Yoast SEO',
			'wordpress-seo-premium/wp-seo-premium.php' => 'Yoast SEO Premium',
			'seo-by-rank-math/rank-math.php'      => 'Rank Math',
			'all-in-one-seo-pack/all_in_one_seo_pack.php' => 'All in One SEO',
			'autodescription/autodescription.php' => 'The SEO Framework',
			'squirrly-seo/squirrly.php'           => 'Squirrly SEO',
			'wp-seopress/seopress.php'            => 'SEOPress',
		);
		$active = (array) get_option( 'active_plugins', array() );
		foreach ( $map as $file => $name ) {
			if ( in_array( $file, $active, true ) ) {
				$detected[] = $name;
			}
		}
		if ( defined( 'RANK_MATH_VERSION' ) && ! in_array( 'Rank Math', $detected, true ) ) {
			$detected[] = 'Rank Math';
		}
		if ( defined( 'WPSEO_VERSION' ) && ! in_array( 'Yoast SEO', $detected, true ) ) {
			$detected[] = 'Yoast SEO';
		}
		return $detected;
	}

	/**
	 * Is another SEO plugin taking care of meta output?
	 *
	 * @return bool
	 */
	public static function other_seo_active() {
		return ! empty( self::seo_plugins() );
	}

	/**
	 * Add the plugin's checks to Tools → Site Health.
	 *
	 * @param array $tests Tests.
	 * @return array
	 */
	public function site_health_tests( $tests ) {
		$tests['direct']['tusb_compat'] = array(
			'label' => __( 'TrustUsBro Site Manager requirements', 'trustusbro-site-manager' ),
			'test'  => function () {
				$report = self::report();
				return array(
					'label'       => $report['ok']
						? __( 'TrustUsBro Site Manager can save your changes', 'trustusbro-site-manager' )
						: __( 'TrustUsBro Site Manager cannot save changes reliably', 'trustusbro-site-manager' ),
					'status'      => $report['ok'] ? 'good' : 'critical',
					'badge'       => array(
						'label' => __( 'Site Manager', 'trustusbro-site-manager' ),
						'color' => 'blue',
					),
					'description' => '<p>' . esc_html( sprintf(
						/* translators: 1: PHP version, 2: WordPress version. */
						__( 'PHP %1$s · WordPress %2$s. Every check below must pass for editing to be reliable. Your existing content is never modified by these checks.', 'trustusbro-site-manager' ),
						$report['php_version'],
						$report['wp_version']
					) ) . '</p>',
					'actions'     => '',
					'test'        => 'tusb_compat',
				);
			},
		);
		return $tests;
	}

	/**
	 * Show a warning when a hard requirement is missing.
	 *
	 * @return void
	 */
	public function notices() {
		if ( ! current_user_can( 'activate_plugins' ) ) {
			return;
		}
		$report = self::report();
		if ( $report['ok'] ) {
			return;
		}
		echo '<div class="notice notice-error"><p><strong>' . esc_html__( 'TrustUsBro Site Manager:', 'trustusbro-site-manager' ) . '</strong> ';
		$parts = array();
		foreach ( $report['blocking'] as $key => $check ) {
			$parts[] = sprintf( '%s (%s, %s)', esc_html( $check['label'] ), esc_html( $check['value'] ), esc_html( $check['need'] ) );
		}
		echo esc_html__( 'Some requirements are not met, so editing will not work reliably:', 'trustusbro-site-manager' );
		echo ' ' . wp_kses_post( implode( ', ', $parts ) ) . '. ';
		echo esc_html__( 'Your website content is safe and untouched. Fix the requirements, then reload.', 'trustusbro-site-manager' );
		echo '</p></div>';
	}
}
