<?php
/**
 * Admin: the TrustUsBro Site Manager dashboard.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Admin.
 */
class TUSB_Admin {

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		add_action( 'admin_menu', array( $this, 'menu' ) );
		add_action( 'admin_enqueue_scripts', array( $this, 'enqueue' ) );
		add_action( 'admin_notices', array( $this, 'first_run_notice' ) );
		add_action( 'wp_dashboard_setup', array( $this, 'dashboard_widget' ) );
		add_filter( 'plugin_action_links_' . TUSB_BASENAME, array( $this, 'action_links' ) );
		add_action( 'admin_post_tusb_dismiss_welcome', array( $this, 'dismiss_welcome' ) );
	}

	/**
	 * Admin menu.
	 *
	 * @return void
	 */
	public function menu() {
		$cap = TUSB_Capabilities::MANAGE;

		add_menu_page(
			__( 'TrustUsBro Site Manager', 'trustusbro-site-manager' ),
			__( 'TrustUsBro', 'trustusbro-site-manager' ),
			$cap,
			'tusb-dashboard',
			array( $this, 'render_app' ),
			'dashicons-art',
			3
		);

		$pages = array(
			'tusb-dashboard'       => array( __( 'Overview', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-pages'           => array( __( 'Pages', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-services'        => array( __( 'Services', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-industries'      => array( __( 'Industries', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-case-studies'    => array( __( 'Case studies', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-testimonials'    => array( __( 'Testimonials', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-faq'             => array( __( 'FAQ', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-header'          => array( __( 'Header', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-footer'          => array( __( 'Footer', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-contact'         => array( __( 'Contact details', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-blog'            => array( __( 'Blog', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-seo'             => array( __( 'SEO', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-media'           => array( __( 'Media', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-design'          => array( __( 'Design settings', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-backups'         => array( __( 'Backups', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-revisions'       => array( __( 'Revision history', 'trustusbro-site-manager' ), 'render_app' ),
			'tusb-health'          => array( __( 'Health & help', 'trustusbro-site-manager' ), 'render_app' ),
		);

		foreach ( $pages as $slug => $config ) {
			add_submenu_page(
				'tusb-dashboard',
				$config[0] . ' — ' . __( 'TrustUsBro Site Manager', 'trustusbro-site-manager' ),
				$config[0],
				$cap,
				$slug,
				array( $this, $config[1] )
			);
		}
	}

	/**
	 * Enqueue dashboard assets only on our screens.
	 *
	 * @param string $hook Current admin page hook.
	 * @return void
	 */
	public function enqueue( $hook ) {
		if ( false === strpos( (string) $hook, 'tusb-' ) ) {
			return;
		}

		wp_enqueue_media();

		wp_enqueue_style(
			'tusb-admin',
			TUSB_URL . 'assets/css/admin.css',
			array( 'wp-components' ),
			TUSB_VERSION
		);

		wp_enqueue_script(
			'tusb-admin',
			TUSB_URL . 'assets/js/admin.js',
			array( 'wp-api-fetch', 'wp-i18n', 'media-editor' ),
			TUSB_VERSION,
			true
		);

		wp_localize_script(
			'tusb-admin',
			'TUSB',
			array(
				'restUrl'   => esc_url_raw( rest_url( TUSB_REST::NS . '/' ) ),
				'nonce'     => wp_create_nonce( 'wp_rest' ),
				'adminUrl'  => admin_url(),
				'pageUrl'   => admin_url( 'admin.php' ),
				'siteUrl'   => home_url( '/' ),
				'view'      => $this->current_view(),
				'version'   => TUSB_VERSION,
				'canManage' => TUSB_Capabilities::can_manage(),
				'canRestore'=> TUSB_Capabilities::can_restore(),
				'media'     => array(
					'libraryTitle'  => __( 'Choose an image', 'trustusbro-site-manager' ),
					'libraryButton' => __( 'Use this image', 'trustusbro-site-manager' ),
					'removeTitle'   => __( 'Remove image', 'trustusbro-site-manager' ),
				),
				// Deep links used by the "go do this in WordPress" buttons. Built in PHP so
				// no URL is ever hard-coded in JavaScript.
				'links'     => array(
					'new_post'   => admin_url( 'post-new.php' ),
					'permalinks' => admin_url( 'options-permalink.php' ),
					'media'      => admin_url( 'upload.php' ),
					'posts'      => admin_url( 'edit.php' ),
					'pages'      => admin_url( 'edit.php?post_type=page' ),
					'dashboard'  => admin_url( 'admin.php?page=tusb-dashboard' ),
					'site'       => home_url( '/' ),
				),
			)
		);

		wp_set_script_translations( 'tusb-admin', 'trustusbro-site-manager', TUSB_DIR . 'languages' );
	}

	/**
	 * Current dashboard view key derived from the page slug.
	 *
	 * @return string
	 */
	private function current_view() {
		$page = isset( $_GET['page'] ) ? sanitize_key( wp_unslash( $_GET['page'] ) ) : 'tusb-dashboard'; // phpcs:ignore WordPress.Security.NonceVerification.Recommended
		$map  = array(
			'tusb-dashboard'    => 'dashboard',
			'tusb-pages'        => 'pages',
			'tusb-services'     => 'services',
			'tusb-industries'   => 'industries',
			'tusb-case-studies' => 'case_studies',
			'tusb-testimonials' => 'testimonials',
			'tusb-faq'          => 'faq',
			'tusb-header'       => 'header',
			'tusb-footer'       => 'footer',
			'tusb-contact'      => 'contact',
			'tusb-blog'         => 'blog',
			'tusb-seo'          => 'seo',
			'tusb-media'        => 'media',
			'tusb-design'       => 'design',
			'tusb-backups'      => 'backups',
			'tusb-revisions'    => 'revisions',
			'tusb-health'       => 'health',
		);
		return isset( $map[ $page ] ) ? $map[ $page ] : 'dashboard';
	}

	/**
	 * Render the dashboard shell. All content is rendered client-side from the
	 * REST bootstrap payload, so the UI is instantly consistent everywhere.
	 *
	 * @return void
	 */
	public function render_app() {
		if ( ! TUSB_Capabilities::can_manage() ) {
			wp_die( esc_html__( 'You do not have permission to manage this website.', 'trustusbro-site-manager' ), 403 );
		}

		$view  = $this->current_view();
		$doc   = isset( $_GET['doc'] ) ? sanitize_key( wp_unslash( $_GET['doc'] ) ) : ''; // phpcs:ignore WordPress.Security.NonceVerification.Recommended
		$health = TUSB_Compat::report();
		?>
		<div class="wrap tusb-wrap">
			<div id="tusb-app" class="tusb-app" data-view="<?php echo esc_attr( $view ); ?>" data-doc="<?php echo esc_attr( $doc ); ?>">
				<div class="tusb-loading">
					<span class="spinner is-active"></span>
					<p><?php esc_html_e( 'Loading TrustUsBro Site Manager…', 'trustusbro-site-manager' ); ?></p>
				</div>
			</div>
			<noscript>
				<div class="notice notice-error"><p><?php esc_html_e( 'The Site Manager dashboard needs JavaScript. Please enable it in your browser.', 'trustusbro-site-manager' ); ?></p></div>
			</noscript>
			<?php if ( ! $health['ok'] ) : ?>
				<div class="tusb-boot-warning">
					<strong><?php esc_html_e( 'Some requirements are not met:', 'trustusbro-site-manager' ); ?></strong>
					<ul>
						<?php foreach ( $health['blocking'] as $check ) : ?>
							<li><?php echo esc_html( $check['label'] . ' — ' . $check['value'] . ' (' . $check['need'] . ')' ); ?>: <?php echo esc_html( $check['advice'] ); ?></li>
						<?php endforeach; ?>
					</ul>
				</div>
			<?php endif; ?>
		</div>
		<?php
	}

	/**
	 * Friendly first-run notice pointing at the dashboard.
	 *
	 * @return void
	 */
	public function first_run_notice() {
		if ( ! TUSB_Capabilities::can_manage() ) {
			return;
		}
		if ( get_option( 'tusb_settings' ) && ! empty( TUSB_Settings::get( 'welcome_dismissed' ) ) ) {
			return;
		}
		$screen = get_current_screen();
		if ( $screen && false !== strpos( (string) $screen->id, 'tusb-' ) ) {
			return;
		}
		?>
		<div class="notice notice-info is-dismissible tusb-welcome">
			<p>
				<strong><?php esc_html_e( 'TrustUsBro Site Manager is ready.', 'trustusbro-site-manager' ); ?></strong>
				<?php esc_html_e( 'Edit your homepage, services, header, footer and SEO from one simple dashboard.', 'trustusbro-site-manager' ); ?>
				<a class="button button-primary" href="<?php echo esc_url( admin_url( 'admin.php?page=tusb-dashboard' ) ); ?>"><?php esc_html_e( 'Open Site Manager', 'trustusbro-site-manager' ); ?></a>
			</p>
		</div>
		<?php
	}

	/**
	 * At-a-glance widget on the WordPress dashboard.
	 *
	 * @return void
	 */
	public function dashboard_widget() {
		if ( ! TUSB_Capabilities::can_manage() ) {
			return;
		}
		wp_add_dashboard_widget(
			'tusb_glance',
			__( 'TrustUsBro Site Manager', 'trustusbro-site-manager' ),
			function () {
				$store  = tusb()->module( 'store' );
				$status = $store ? $store->status() : array();
				$pending = array();
				foreach ( $status as $key => $row ) {
					if ( ! empty( $row['has_unpublished'] ) ) {
						$pending[] = $row['label'];
					}
				}
				echo '<p>';
				if ( $pending ) {
					printf(
						/* translators: %s: comma separated document names. */
						esc_html__( 'Changes waiting to be published: %s', 'trustusbro-site-manager' ),
						'<strong>' . esc_html( implode( ', ', $pending ) ) . '</strong>'
					);
				} else {
					esc_html_e( 'All published content is up to date.', 'trustusbro-site-manager' );
				}
				echo '</p>';
				echo '<p><a class="button button-primary" href="' . esc_url( admin_url( 'admin.php?page=tusb-dashboard' ) ) . '">' . esc_html__( 'Open Site Manager', 'trustusbro-site-manager' ) . '</a> ';
				echo '<a class="button" href="' . esc_url( admin_url( 'admin.php?page=tusb-backups' ) ) . '">' . esc_html__( 'Backups', 'trustusbro-site-manager' ) . '</a></p>';
			}
		);
	}

	/**
	 * Plugin row action links.
	 *
	 * @param array $links Links.
	 * @return array
	 */
	public function action_links( $links ) {
		$links = array_merge(
			array(
				'<a href="' . esc_url( admin_url( 'admin.php?page=tusb-dashboard' ) ) . '">' . esc_html__( 'Dashboard', 'trustusbro-site-manager' ) . '</a>',
				'<a href="' . esc_url( admin_url( 'admin.php?page=tusb-health' ) ) . '">' . esc_html__( 'Help', 'trustusbro-site-manager' ) . '</a>',
			),
			$links
		);
		return $links;
	}

	/**
	 * Dismiss the welcome notice.
	 *
	 * @return void
	 */
	public function dismiss_welcome() {
		if ( ! TUSB_Capabilities::can_manage() ) {
			wp_die( esc_html__( 'Not allowed.', 'trustusbro-site-manager' ), 403 );
		}
		check_admin_referer( 'tusb_dismiss_welcome' );
		TUSB_Settings::set( 'welcome_dismissed', true );
		wp_safe_redirect( wp_get_referer() ? wp_get_referer() : admin_url() );
		exit;
	}
}
