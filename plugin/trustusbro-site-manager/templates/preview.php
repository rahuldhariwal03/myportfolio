<?php
/**
 * Standalone preview template.
 *
 * Renders drafts for signed-in editors without depending on the active theme's
 * templates, but still loads the theme's stylesheets so the preview matches the
 * real site as closely as possible.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

$tusb_doc   = tusb_preview_doc();
$tusb_store = tusb()->module( 'store' );
$tusb_renderer = tusb()->module( 'renderer' );

if ( ! $tusb_doc || ! $tusb_renderer ) {
	wp_safe_redirect( home_url( '/' ) );
	exit;
}

$tusb_back = admin_url( 'admin.php?page=' . ( 'header' === $tusb_doc || 'footer' === $tusb_doc || 'contact' === $tusb_doc || 'design' === $tusb_doc ? 'tusb-' . str_replace( '_', '-', $tusb_doc ) : ( in_array( $tusb_doc, array( 'home', 'about' ), true ) ? 'tusb-pages' : 'tusb-' . str_replace( '_', '-', $tusb_doc ) ) ) );
$tusb_meta = $tusb_store ? $tusb_store->meta( $tusb_doc ) : array();
?>
<!DOCTYPE html>
<html <?php language_attributes(); ?>>
<head>
	<meta charset="<?php bloginfo( 'charset' ); ?>" />
	<meta name="viewport" content="width=device-width, initial-scale=1" />
	<meta name="robots" content="noindex, nofollow" />
	<title><?php echo esc_html( sprintf( /* translators: %s: document label. */ __( 'Preview: %s', 'trustusbro-site-manager' ), tusb_doc_label( $tusb_doc ) ) ); ?></title>
	<?php
	// Load the active theme's styles so the preview inherits the real design.
	wp_enqueue_style( 'tusb-site' );
	wp_head();
	?>
	<style>
		body.tusb-preview-body { margin: 0; padding: 0; }
		.tusb-preview-body.admin-bar { padding-top: 0; }
		.tusb-preview-shell { padding-bottom: 0; }
	</style>
</head>
<body <?php body_class( 'tusb-preview-body' ); ?>>
	<div class="tusb-preview-banner">
		<span>
			<span class="tusb-preview-banner__tag"><?php esc_html_e( 'Draft preview', 'trustusbro-site-manager' ); ?></span>
			<?php
			printf(
				/* translators: 1: document label, 2: human readable time. */
				esc_html__( 'Showing the unpublished draft of %1$s, saved %2$s. Visitors still see the published version.', 'trustusbro-site-manager' ),
				esc_html( tusb_doc_label( $tusb_doc ) ),
				esc_html( tusb_time_diff( isset( $tusb_meta['draft_modified'] ) ? (int) $tusb_meta['draft_modified'] : 0 ) )
			);
			?>
		</span>
		<span>
			<a href="<?php echo esc_url( $tusb_back ); ?>"><?php esc_html_e( '← Back to the editor', 'trustusbro-site-manager' ); ?></a>
			&nbsp;·&nbsp;
			<a href="<?php echo esc_url( home_url( '/' ) ); ?>"><?php esc_html_e( 'Published site', 'trustusbro-site-manager' ); ?></a>
		</span>
	</div>

	<?php if ( 'home' === $tusb_doc || 'about' === $tusb_doc ) : ?>
		<?php
		$tusb_show_header = true;
		if ( $tusb_show_header && $tusb_renderer instanceof TUSB_Renderer ) {
			$tusb_renderer->header();
		}
		?>
		<main class="tusb-preview-shell" id="tusb-preview-main">
			<?php echo $tusb_renderer->render_preview_body( $tusb_doc ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped in renderer. ?>
		</main>
		<?php
		if ( $tusb_show_header && $tusb_renderer instanceof TUSB_Renderer ) {
			$tusb_renderer->footer();
		}
		?>
	<?php else : ?>
		<main class="tusb-preview-shell" id="tusb-preview-main">
			<?php echo $tusb_renderer->render_preview_body( $tusb_doc ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- escaped in renderer. ?>
		</main>
	<?php endif; ?>

	<?php wp_footer(); ?>
	<script>
		// Keep previews out of caches and search engines even behind a proxy.
		document.documentElement.setAttribute('data-tusb-preview', '1');
	</script>
</body>
</html>
