<?php
/**
 * Plugin Name:       TrustUsBro Site Manager
 * Plugin URI:        https://example.com/trustusbro-site-manager
 * Description:       Beginner-friendly, dashboard-first website management for TrustUsBro. Click-to-edit and drag-and-drop editing of every section, with drafts, revisions, backups and SEO controls. Theme agnostic: inherits the active theme's design tokens instead of imposing a new design.
 * Version:           1.0.0
 * Requires at least: 6.0
 * Requires PHP:      7.4
 * Author:            TrustUsBro
 * License:           GPL-2.0-or-later
 * License URI:       https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain:       trustusbro-site-manager
 * Domain Path:       /languages
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

define( 'TUSB_VERSION', '1.0.0' );
define( 'TUSB_FILE', __FILE__ );
define( 'TUSB_DIR', plugin_dir_path( __FILE__ ) );
define( 'TUSB_URL', plugin_dir_url( __FILE__ ) );
define( 'TUSB_BASENAME', plugin_basename( __FILE__ ) );
define( 'TUSB_DOC_CPT', 'tusb_content' );
define( 'TUSB_CONTENT_VERSION', 1 );

require_once TUSB_DIR . 'includes/functions.php';

/**
 * Main plugin bootstrapper.
 */
final class TUSB_Plugin {

	/**
	 * Singleton instance.
	 *
	 * @var TUSB_Plugin|null
	 */
	private static $instance = null;

	/**
	 * Loaded module instances, keyed by short name.
	 *
	 * @var array<string,object>
	 */
	public $modules = array();

	/**
	 * Get the singleton.
	 *
	 * @return TUSB_Plugin
	 */
	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	/**
	 * Constructor: wire up files and hooks.
	 */
	private function __construct() {
		$this->load_files();
		$this->init_modules();
	}

	/**
	 * Require the plugin's class files.
	 *
	 * @return void
	 */
	private function load_files() {
		$files = array(
			'includes/class-compat.php',
			'includes/class-capabilities.php',
			'includes/class-schema.php',
			'includes/class-sanitizer.php',
			'includes/class-content-store.php',
			'includes/class-settings.php',
			'includes/class-design.php',
			'includes/class-renderer.php',
			'includes/class-media.php',
			'includes/class-backup.php',
			'includes/class-seo.php',
			'includes/class-blog.php',
			'includes/class-forms.php',
			'includes/class-rest.php',
			'includes/class-admin.php',
		);

		foreach ( $files as $file ) {
			$path = TUSB_DIR . $file;
			if ( is_readable( $path ) ) {
				require_once $path;
			}
		}
	}

	/**
	 * Instantiate modules and register their hooks.
	 *
	 * Every module is defensive: a failure in one must never take the site down.
	 *
	 * @return void
	 */
	private function init_modules() {
		$classes = array(
			'compat'      => 'TUSB_Compat',
			'capabilities'=> 'TUSB_Capabilities',
			'store'       => 'TUSB_Content_Store',
			'settings'    => 'TUSB_Settings',
			'design'      => 'TUSB_Design',
			'renderer'    => 'TUSB_Renderer',
			'media'       => 'TUSB_Media',
			'backup'      => 'TUSB_Backup',
			'seo'         => 'TUSB_SEO',
			'blog'        => 'TUSB_Blog',
			'forms'       => 'TUSB_Forms',
			'rest'        => 'TUSB_REST',
			'admin'       => 'TUSB_Admin',
		);

		foreach ( $classes as $key => $class_name ) {
			if ( ! class_exists( $class_name ) ) {
				continue;
			}
			try {
				$module = new $class_name();
				if ( method_exists( $module, 'hooks' ) ) {
					$module->hooks();
				}
				$this->modules[ $key ] = $module;
			} catch ( Throwable $e ) {
				tusb_log( sprintf( 'Module %s failed to initialise: %s', $class_name, $e->getMessage() ) );
			}
		}

		add_action( 'plugins_loaded', array( $this, 'load_textdomain' ) );
	}

	/**
	 * Convenience accessor for modules.
	 *
	 * @param string $key Module key.
	 * @return object|null
	 */
	public function module( $key ) {
		return isset( $this->modules[ $key ] ) ? $this->modules[ $key ] : null;
	}

	/**
	 * Load translations.
	 *
	 * @return void
	 */
	public function load_textdomain() {
		load_plugin_textdomain( 'trustusbro-site-manager', false, dirname( TUSB_BASENAME ) . '/languages' );
	}
}

/**
 * Boot.
 *
 * @return TUSB_Plugin
 */
function tusb() {
	return TUSB_Plugin::instance();
}

tusb();

/*
 * Activation / deactivation.
 */
register_activation_hook(
	__FILE__,
	static function ( $network_wide = false ) {
		require_once TUSB_DIR . 'includes/class-activator.php';
		TUSB_Activator::activate( $network_wide );
	}
);

register_deactivation_hook(
	__FILE__,
	static function ( $network_wide = false ) {
		require_once TUSB_DIR . 'includes/class-activator.php';
		TUSB_Activator::deactivate( $network_wide );
	}
);
