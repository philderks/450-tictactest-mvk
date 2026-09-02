package ch.bbw.m450.tictactoe;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;
import ch.bbw.m450.tictactoe.players.GreedyPlayer;
import org.junit.jupiter.api.Test;

class TicTacToeMainTest {

	// fixtures: named boards reused across the tests below
	private static final Stone[] ROW_WIN_CROSS = {
			Stone.CROSS, Stone.CROSS, Stone.CROSS,
			null, Stone.CIRCLE, null,
			Stone.CIRCLE, null, null
	};

	private static final Stone[] DIAGONAL_WIN_CROSS = {
			Stone.CIRCLE, null, Stone.CROSS,
			null, Stone.CROSS, null,
			Stone.CROSS, null, Stone.CIRCLE
	};

	private static final Stone[] FULL_BOARD_NO_WINNER = {
			Stone.CROSS, Stone.CIRCLE, Stone.CROSS,
			Stone.CROSS, Stone.CIRCLE, Stone.CIRCLE,
			Stone.CIRCLE, Stone.CROSS, Stone.CROSS
	};

	@Test
	void isWin_detectsRowWin() {
		assertThat(TicTacToeMain.isWin(ROW_WIN_CROSS, Stone.CROSS)).isTrue();
		assertThat(TicTacToeMain.isWin(ROW_WIN_CROSS, Stone.CIRCLE)).isFalse();
	}

	@Test
	void isWin_detectsDiagonalWin() {
		assertThat(TicTacToeMain.isWin(DIAGONAL_WIN_CROSS, Stone.CROSS)).isTrue();
	}

	@Test
	void isWin_returnsFalseForNonWinningBoard() {
		assertThat(TicTacToeMain.isWin(FULL_BOARD_NO_WINNER, Stone.CROSS)).isFalse();
		assertThat(TicTacToeMain.isWin(FULL_BOARD_NO_WINNER, Stone.CIRCLE)).isFalse();
	}

	@Test
	void play_throwsIllegalArgumentException_whenSamePlayerInstanceUsedForBothSides() {
		var player = new GreedyPlayer();

		assertThatThrownBy(() -> TicTacToeMain.play(player, player))
				.isInstanceOf(IllegalArgumentException.class);
	}

	@Test
	void play_withTwoGreedyPlayers_producesDeterministicCrossWin() {
		// GreedyPlayer always fills the first free field: X takes 0,2,4,6 and
		// wins via the 2-4-6 anti-diagonal before O gets to move a 4th time.
		var winner = TicTacToeMain.play(new GreedyPlayer(), new GreedyPlayer());

		assertThat(winner).isEqualTo(Stone.CROSS);
	}
}
