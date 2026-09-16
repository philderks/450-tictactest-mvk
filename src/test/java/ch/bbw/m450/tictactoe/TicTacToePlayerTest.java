package ch.bbw.m450.tictactoe;

import static org.assertj.core.api.Assertions.assertThat;

import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;
import org.junit.jupiter.api.Test;

class TicTacToePlayerTest {

	@Test
	void opponent_ofCrossIsCircle() {
		assertThat(Stone.CROSS.opponent()).isEqualTo(Stone.CIRCLE);
	}

	@Test
	void opponent_ofCircleIsCross() {
		assertThat(Stone.CIRCLE.opponent()).isEqualTo(Stone.CROSS);
	}
}
